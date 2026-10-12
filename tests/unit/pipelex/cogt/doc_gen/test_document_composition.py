from pathlib import Path

import pytest
from pydantic import ValidationError

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.document_composition import DocumentComposition
from pipelex.cogt.doc_gen.layout_tree import ImageBlock, LayoutDocument, SectionBlock
from pipelex.core.bundle_resources.bundle_resource import BundleResource
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider


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

    @pytest.mark.asyncio
    async def test_the_render_job_carries_the_template_file_s_bytes(self, tmp_path: Path) -> None:
        template_file = tmp_path / "invoice.docx"
        template_file.write_bytes(b"docx bytes")
        composition = DocumentComposition(
            format=DocGenFormat.DOCX,
            source=DocGenSource.TEMPLATE_FILE,
            filename="invoice.docx",
            title="Invoice",
            template_path=str(template_file),
            template_name="invoice.docx",
            data={"invoice": {"number": "INV-1"}},
        )

        job = await composition.make_render_job(storage_provider=InMemoryStorageProvider())

        assert job.template == b"docx bytes"
        assert job.template_name == "invoice.docx"
        assert job.data == {"invoice": {"number": "INV-1"}}

    @pytest.mark.asyncio
    async def test_a_template_file_submitted_with_its_bundle_is_read_from_its_resource(self) -> None:
        """Inline, the bytes are the composition's own; stored, they are read back through the run's storage, under its read scope."""
        storage_provider = InMemoryStorageProvider()
        inline = BundleResource.make_inline(content=b"docx bytes")
        uri = await storage_provider.store(b"docx bytes", key="org/run/assets/bundle/digest/invoice.docx")
        stored = inline.stored_at(uri=uri)

        for resource in (inline, stored):
            composition = DocumentComposition(
                format=DocGenFormat.DOCX,
                source=DocGenSource.TEMPLATE_FILE,
                filename="invoice.docx",
                title="Invoice",
                template_resource=resource,
                template_name="invoice.docx",
            )
            job = await composition.make_render_job(storage_provider=storage_provider)
            assert job.template == b"docx bytes"

        stored_composition = DocumentComposition(
            format=DocGenFormat.DOCX,
            source=DocGenSource.TEMPLATE_FILE,
            filename="invoice.docx",
            title="Invoice",
            template_resource=stored,
            template_name="invoice.docx",
        )
        (uri_reference,) = stored_composition.referenced_uris()
        assert uri_reference.uri == uri
        assert uri_reference.position == "the template file 'invoice.docx'"

    def test_a_template_file_read_from_disk_and_from_its_resource_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="not both"):
            DocumentComposition(
                format=DocGenFormat.DOCX,
                source=DocGenSource.TEMPLATE_FILE,
                filename="invoice.docx",
                title="Invoice",
                template_path="/nowhere/invoice.docx",
                template_resource=BundleResource.make_inline(content=b"docx bytes"),
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
                template_path="/nowhere/report.docx",
            )
