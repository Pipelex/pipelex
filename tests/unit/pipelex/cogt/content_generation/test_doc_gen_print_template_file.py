"""The print stage of a PipeDocGen step reads its template file through the method file store, where IO is allowed.

The compose stage names the file by its tree's digest and its tree path; the print reads it under the run's read scope,
renders an HTML one through the interpreter's template file stage, and hands an office one's bytes to its engine.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation import doc_gen_generate
from pipelex.cogt.content_generation.assignment_models import RenderDocumentAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenSetting
from pipelex.cogt.doc_gen.document_composition import ComposedTemplateFile, DocumentComposition, TemplateRenderContext
from pipelex.cogt.doc_gen.exceptions import DocGenRenderError
from pipelex.core.method_trees.tree_bundle import MethodFileRef
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode

_FILE = MethodFileRef(tree_digest="sha256:" + "1" * 64, tree_path="templates/invoice.html")


def _assignment(*, composition: DocumentComposition) -> RenderDocumentAssignment:
    return RenderDocumentAssignment(
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(user_id="u", pipeline_run_id="run_1", storage_scope="acme/runs/run_1", read_scope="acme/runs")
        ),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
        composition=composition,
        doc_gen_setting=DocGenSetting(model="pipelex-pdf"),
    )


def _html_template_file() -> ComposedTemplateFile:
    return ComposedTemplateFile(
        file=_FILE,
        name="templates/invoice.html",
        pipe_ref="invoicing.print_invoice",
        render_context=TemplateRenderContext(crate_fingerprint="", concepts_crate={}, working_memory_raw={}),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestDocGenPrintTemplateFile:
    async def test_an_html_template_file_is_read_under_the_run_s_read_scope_and_rendered(self, mocker: MockerFixture) -> None:
        read_spy = mocker.patch.object(doc_gen_generate, "read_method_file", new=mocker.AsyncMock(return_value=b"<h1>{{ invoice.number }}</h1>"))
        stage = mocker.MagicMock()
        stage.render_html_template_file = mocker.AsyncMock(return_value="<h1>INV-1</h1>")
        mocker.patch.object(doc_gen_generate, "get_template_file_stage", return_value=stage)
        template_file = _html_template_file()
        composition = DocumentComposition(
            format=DocGenFormat.PDF, source=DocGenSource.HTML, filename="invoice.pdf", title="Invoice", template_file=template_file
        )

        read_template = await doc_gen_generate.read_template_file(render_assignment=_assignment(composition=composition))

        assert read_template.html == "<h1>INV-1</h1>"
        assert read_template.template is None
        read_spy.assert_awaited_once_with(file_ref=_FILE, read_scope="acme/runs")
        stage.render_html_template_file.assert_awaited_once_with(template_file=template_file, template_source="<h1>{{ invoice.number }}</h1>")

    async def test_an_office_template_file_s_bytes_go_to_the_engine_unrendered(self, mocker: MockerFixture) -> None:
        mocker.patch.object(doc_gen_generate, "read_method_file", new=mocker.AsyncMock(return_value=b"PK docx"))
        stage_getter = mocker.patch.object(doc_gen_generate, "get_template_file_stage")
        composition = DocumentComposition(
            format=DocGenFormat.DOCX,
            source=DocGenSource.TEMPLATE_FILE,
            filename="invoice.docx",
            title="Invoice",
            template_file=ComposedTemplateFile(file=_FILE, name="invoice.docx", pipe_ref="invoicing.print_invoice"),
        )

        read_template = await doc_gen_generate.read_template_file(render_assignment=_assignment(composition=composition))

        assert read_template.template == b"PK docx"
        assert read_template.html is None
        stage_getter.assert_not_called()

    async def test_an_html_template_file_that_is_not_utf8_fails_the_print_naming_it(self, mocker: MockerFixture) -> None:
        mocker.patch.object(doc_gen_generate, "read_method_file", new=mocker.AsyncMock(return_value="<p>émise</p>".encode("latin-1")))
        composition = DocumentComposition(
            format=DocGenFormat.PDF, source=DocGenSource.HTML, filename="invoice.pdf", title="Invoice", template_file=_html_template_file()
        )

        with pytest.raises(DocGenRenderError, match=r"'templates/invoice\.html'.*not UTF-8"):
            await doc_gen_generate.read_template_file(render_assignment=_assignment(composition=composition))

    async def test_a_document_printed_from_no_template_file_reads_nothing(self, mocker: MockerFixture) -> None:
        read_spy = mocker.patch.object(doc_gen_generate, "read_method_file", new=mocker.AsyncMock())
        composition = DocumentComposition(format=DocGenFormat.PDF, source=DocGenSource.HTML, filename="invoice.pdf", title="Invoice", html="<p>x</p>")

        read_template = await doc_gen_generate.read_template_file(render_assignment=_assignment(composition=composition))

        assert read_template == (None, None)
        read_spy.assert_not_awaited()
