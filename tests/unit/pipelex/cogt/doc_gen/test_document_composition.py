import pytest
from pydantic import ValidationError

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.document_composition import ComposedTemplateFile, DocumentComposition, TemplateRenderContext
from pipelex.cogt.doc_gen.layout_tree import ImageBlock, LayoutDocument, SectionBlock
from pipelex.core.method_trees.tree_bundle import MethodFileRef

_TREE_DIGEST = "sha256:" + "a" * 64

_OFFICE_TEMPLATE_FILE = ComposedTemplateFile(
    file=MethodFileRef(tree_digest=_TREE_DIGEST, tree_path="templates/invoice.docx"),
    name="templates/invoice.docx",
    pipe_ref="invoicing.print_invoice",
)

_HTML_TEMPLATE_FILE = ComposedTemplateFile(
    file=MethodFileRef(tree_digest=_TREE_DIGEST, tree_path="templates/report.html"),
    name="templates/report.html",
    pipe_ref="invoicing.print_report",
    render_context=TemplateRenderContext(crate={}, working_memory_raw={}),
)


class TestDocumentComposition:
    def test_its_images_are_what_the_print_stage_reads(self) -> None:
        composition = DocumentComposition(
            format=DocGenFormat.PDF,
            source=DocGenSource.LAYOUT,
            filename="report.pdf",
            title="Report",
            layout=LayoutDocument(
                title="Report",
                blocks=[
                    ImageBlock(url="pipelex-storage://s/cover.png"),
                    SectionBlock(
                        title="Figures",
                        level=1,
                        blocks=[
                            ImageBlock(url="https://example.com/figure.png"),
                            SectionBlock(title="Detail", level=2, blocks=[ImageBlock(url="https://example.com/detail.png")]),
                        ],
                    ),
                ],
            ),
        )

        uri_references = composition.referenced_uris()

        assert [uri_reference.uri for uri_reference in uri_references] == [
            "pipelex-storage://s/cover.png",
            "https://example.com/figure.png",
            "https://example.com/detail.png",
        ]
        assert uri_references[1].position == "image 2 of the document 'report.pdf'"

    def test_composed_html_declares_no_read(self) -> None:
        composition = DocumentComposition(
            format=DocGenFormat.PDF, source=DocGenSource.HTML, filename="report.pdf", title="Report", html='<img src="https://example.com/a.png">'
        )
        assert composition.referenced_uris() == []

    def test_the_render_job_carries_what_the_print_stage_read(self) -> None:
        composition = DocumentComposition(
            format=DocGenFormat.DOCX,
            source=DocGenSource.TEMPLATE_FILE,
            filename="invoice.docx",
            title="Invoice",
            template_file=_OFFICE_TEMPLATE_FILE,
            data={"invoice": {"number": "INV-1"}},
        )

        job = composition.make_render_job(template=b"docx bytes")

        assert job.template == b"docx bytes"
        assert job.template_name == "templates/invoice.docx"
        assert job.data == {"invoice": {"number": "INV-1"}}

    def test_an_html_template_file_prints_as_the_html_the_print_stage_rendered(self) -> None:
        composition = DocumentComposition(
            format=DocGenFormat.PDF, source=DocGenSource.HTML, filename="report.pdf", title="Report", template_file=_HTML_TEMPLATE_FILE
        )

        job = composition.make_render_job(html="<p>INV-1</p>")

        assert composition.renders_html_template_file
        assert job.html == "<p>INV-1</p>"
        assert job.template is None

    def test_a_template_file_travels_by_its_tree_and_tree_path_never_its_bytes(self) -> None:
        """The composition crosses a workflow boundary, so it names the file and the print stage reads it."""
        composition = DocumentComposition(
            format=DocGenFormat.DOCX,
            source=DocGenSource.TEMPLATE_FILE,
            filename="invoice.docx",
            title="Invoice",
            template_file=_OFFICE_TEMPLATE_FILE,
        )

        restored = DocumentComposition.model_validate_json(composition.model_dump_json())

        assert restored == composition
        assert restored.template_file is not None
        assert restored.template_file.file == MethodFileRef(tree_digest=_TREE_DIGEST, tree_path="templates/invoice.docx")
        assert composition.referenced_uris() == []

    def test_rendered_html_and_a_template_file_to_render_are_refused_together(self) -> None:
        with pytest.raises(ValidationError, match="not both"):
            DocumentComposition(
                format=DocGenFormat.PDF,
                source=DocGenSource.HTML,
                filename="report.pdf",
                title="Report",
                html="<p>Report</p>",
                template_file=_HTML_TEMPLATE_FILE,
            )

    def test_a_composition_without_its_payload_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="carries its payload"):
            DocumentComposition(format=DocGenFormat.DOCX, source=DocGenSource.TEMPLATE_FILE, filename="invoice.docx", title="Invoice")

    def test_a_composition_with_another_source_s_payload_too_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="carries only its own payload, not the template_file one"):
            DocumentComposition(
                format=DocGenFormat.PDF,
                source=DocGenSource.HTML,
                filename="report.pdf",
                title="Report",
                html="<p>Report</p>",
                template_file=_OFFICE_TEMPLATE_FILE,
            )
