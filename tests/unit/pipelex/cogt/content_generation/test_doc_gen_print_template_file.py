"""The print stage of a PipeDocGen step reads its template file through the method file store, where IO is allowed.

The compose stage names the file by its tree's digest and its tree path; the print reads it under the run's read scope,
renders an HTML one through the interpreter's template file stage, and hands an office one's bytes to its engine.
"""

import base64

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation import doc_gen_generate, doc_gen_template_input
from pipelex.cogt.content_generation.assignment_models import RenderDocumentAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenSetting
from pipelex.cogt.doc_gen.document_composition import ComposedTemplateFile, DocumentComposition, TemplateInputFile, TemplateRenderContext
from pipelex.cogt.doc_gen.exceptions import DocGenRenderError, DocGenTemplateInputFormatError, DocGenTemplateInputTooLargeError
from pipelex.cogt.doc_gen.table_fill import TableFill
from pipelex.core.method_trees.tree_bundle import MethodFileRef
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.misc.exceptions import RemoteFileSizeBound, RemoteFileTooLargeError
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.uri.exceptions import UriReadRefusedError
from tests.helpers.office_files import docx_bytes, office_package_bytes, xlsx_bytes

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


def _input_template_composition(
    *, url: str, filename: str | None = "expenses.xlsx", doc_gen_format: DocGenFormat = DocGenFormat.XLSX
) -> DocumentComposition:
    return DocumentComposition(
        format=doc_gen_format,
        source=DocGenSource.TEMPLATE_FILE,
        filename="expenses.xlsx",
        title="Expenses",
        template_file=ComposedTemplateFile(
            file=TemplateInputFile(input_name="workbook", url=url, filename=filename),
            name="the input 'workbook'",
            pipe_ref="expenses.append_rows",
        ),
        table_fill=TableFill.APPEND,
    )


def _input_template_assignment(
    *, composition: DocumentComposition, run_mode: PipeRunMode = PipeRunMode.LIVE, read_scope: str | None = "acme/runs"
) -> RenderDocumentAssignment:
    return RenderDocumentAssignment(
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(user_id="u", pipeline_run_id="run_1", storage_scope="acme/runs/run_1", read_scope=read_scope),
            pipe_code="append_rows",
        ),
        cogt_run_params=CogtRunParams(run_mode=run_mode),
        composition=composition,
        doc_gen_setting=DocGenSetting(model="pipelex-xlsx"),
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

        read_template = await doc_gen_generate.read_template_file(
            render_assignment=_assignment(composition=composition), storage_provider=mocker.MagicMock()
        )

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

        read_template = await doc_gen_generate.read_template_file(
            render_assignment=_assignment(composition=composition), storage_provider=mocker.MagicMock()
        )

        assert read_template.template == b"PK docx"
        assert read_template.html is None
        stage_getter.assert_not_called()

    async def test_an_html_template_file_that_is_not_utf8_fails_the_print_naming_it(self, mocker: MockerFixture) -> None:
        mocker.patch.object(doc_gen_generate, "read_method_file", new=mocker.AsyncMock(return_value="<p>émise</p>".encode("latin-1")))
        composition = DocumentComposition(
            format=DocGenFormat.PDF, source=DocGenSource.HTML, filename="invoice.pdf", title="Invoice", template_file=_html_template_file()
        )

        with pytest.raises(DocGenRenderError, match=r"'templates/invoice\.html'.*not UTF-8"):
            await doc_gen_generate.read_template_file(render_assignment=_assignment(composition=composition), storage_provider=mocker.MagicMock())

    async def test_a_document_printed_from_no_template_file_reads_nothing(self, mocker: MockerFixture) -> None:
        read_spy = mocker.patch.object(doc_gen_generate, "read_method_file", new=mocker.AsyncMock())
        composition = DocumentComposition(format=DocGenFormat.PDF, source=DocGenSource.HTML, filename="invoice.pdf", title="Invoice", html="<p>x</p>")

        read_template = await doc_gen_generate.read_template_file(
            render_assignment=_assignment(composition=composition), storage_provider=mocker.MagicMock()
        )

        assert read_template == (None, None)
        read_spy.assert_not_awaited()

    async def test_a_template_a_run_input_supplies_is_read_from_storage_under_the_run_s_read_scope(self, mocker: MockerFixture) -> None:
        method_file_read = mocker.patch.object(doc_gen_generate, "read_method_file", new=mocker.AsyncMock())
        storage = InMemoryStorageProvider()
        url = await storage.store(data=xlsx_bytes(), key="acme/runs/run_1/inputs/expenses.xlsx")

        read_template = await doc_gen_generate.read_template_file(
            render_assignment=_input_template_assignment(composition=_input_template_composition(url=url)), storage_provider=storage
        )

        assert read_template.template == xlsx_bytes()
        assert read_template.html is None
        method_file_read.assert_not_awaited()

    @pytest.mark.parametrize(
        ("data", "filename", "expected_format", "expected_words"),
        [
            (docx_bytes(), "expenses.xlsx", "docx", "is a Word document (.docx)"),
            (office_package_bytes(main_content_type=None), "expenses.xlsx", "zip", "is a .zip file"),
            (b"%PDF-1.7\n%stub", "expenses.xlsx", "pdf", "is a PDF document (.pdf)"),
            (b"description,amount\nTea,7\n", None, "unknown", "is a file of no known format"),
        ],
        ids=["word_named_xlsx", "zip_without_content_types", "pdf", "text_without_a_name"],
    )
    async def test_a_template_input_of_another_format_is_refused_from_its_bytes(
        self, data: bytes, filename: str | None, expected_format: str, expected_words: str
    ) -> None:
        """The bytes decide, whatever the file is named, and the refusal names the input, never the file or its URL."""
        storage = InMemoryStorageProvider()
        url = await storage.store(data=data, key="acme/runs/run_1/inputs/upload-7f3a")

        with pytest.raises(DocGenTemplateInputFormatError) as exc_info:
            await doc_gen_generate.read_template_file(
                render_assignment=_input_template_assignment(composition=_input_template_composition(url=url, filename=filename)),
                storage_provider=storage,
            )

        error = exc_info.value
        assert error.resolve_error_code() == CoreCode.INPUT_FILE_TYPE_UNSUPPORTED
        assert error.problem_params() == {"input": "workbook", "format": expected_format, "model": "pipelex-xlsx"}
        assert expected_words in error.message
        assert "The input 'workbook'" in error.message
        assert "upload-7f3a" not in error.message
        assert "expenses.xlsx" not in error.message

    async def test_a_template_input_outside_the_run_s_read_scope_is_refused_before_it_is_read(self) -> None:
        storage = InMemoryStorageProvider()
        url = await storage.store(data=xlsx_bytes(), key="other-tenant/expenses.xlsx")

        with pytest.raises(UriReadRefusedError):
            await doc_gen_generate.read_template_file(
                render_assignment=_input_template_assignment(composition=_input_template_composition(url=url)), storage_provider=storage
            )

    @pytest.mark.parametrize("uri_kind", ["storage", "data_url"])
    async def test_a_template_input_past_the_fetch_cap_is_refused_before_it_is_loaded(self, mocker: MockerFixture, uri_kind: str) -> None:
        """A stored file is sized without being read, and a data URL by its text, each against `max_fetch_bytes`."""
        mocker.patch.object(doc_gen_template_input, "fetch_max_bytes", return_value=16)
        load_spy = mocker.spy(doc_gen_template_input, "load_bytes_and_mime_type_from_any_uri")
        storage = InMemoryStorageProvider()
        workbook = xlsx_bytes()
        url: str
        match uri_kind:
            case "storage":
                url = await storage.store(data=workbook, key="acme/runs/run_1/inputs/expenses.xlsx")
            case _:
                url = f"data:application/octet-stream;base64,{base64.b64encode(workbook).decode('ascii')}"

        with pytest.raises(DocGenTemplateInputTooLargeError) as exc_info:
            await doc_gen_generate.read_template_file(
                render_assignment=_input_template_assignment(composition=_input_template_composition(url=url)), storage_provider=storage
            )

        error = exc_info.value
        assert error.resolve_error_code() == CoreCode.INPUT_TOO_LARGE
        assert error.problem_params()["input"] == "workbook"
        assert error.problem_params()["limit"] == 16
        assert error.problem_params()["size"] >= len(workbook) - 2
        load_spy.assert_not_called()

    async def test_a_template_input_at_a_url_is_fetched_under_the_cap_naming_the_input(self, mocker: MockerFixture) -> None:
        mocker.patch.object(doc_gen_template_input, "fetch_max_bytes", return_value=16)
        fetch = mocker.patch(
            "pipelex.tools.uri.uri_bytes.fetch_file_and_content_type_from_url_httpx",
            side_effect=RemoteFileTooLargeError("too large", limit=16, size=4096, bound=RemoteFileSizeBound.DECODED),
        )

        with pytest.raises(RemoteFileTooLargeError) as exc_info:
            await doc_gen_generate.read_template_file(
                render_assignment=_input_template_assignment(
                    composition=_input_template_composition(url="https://files.example.com/expenses.xlsx"), read_scope=None
                ),
                storage_provider=InMemoryStorageProvider(),
            )

        assert fetch.call_args.kwargs["max_bytes"] == 16
        assert exc_info.value.input_name == "workbook"
