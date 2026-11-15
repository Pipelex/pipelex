"""A template a run input supplies, and the fills of a template's Tables, as the document engine contract carries them."""

import io
import struct
import tracemalloc
import zipfile
import zlib
from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.cogt.doc_gen.doc_gen_engine import fills_tables
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.document_composition import ComposedTemplateFile, DocumentComposition, TemplateInputFile, TemplateRenderContext
from pipelex.cogt.doc_gen.exceptions import DocGenModelCapabilityError
from pipelex.cogt.doc_gen.layout_tree import LayoutDocument
from pipelex.cogt.doc_gen.render_job import RenderJob
from pipelex.cogt.doc_gen.table_fill import TABLE_APPEND_CAPABILITY, TableFill
from pipelex.cogt.doc_gen.template_input_format import ZIP_FORMAT_KEY, judge_file_format, office_format_of_zip
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.method_trees.tree_bundle import MethodFileRef
from tests.helpers.office_files import (
    DOCX_MIME_TYPE,
    PPTX_MAIN_CONTENT_TYPE,
    XLSX_MAIN_CONTENT_TYPE,
    XLSX_MIME_TYPE,
    docx_bytes,
    office_package_bytes,
    xlsx_bytes,
)

_INPUT_TEMPLATE_FILE = ComposedTemplateFile(
    file=TemplateInputFile(input_name="workbook", url="pipelex-storage://acme/runs/r1/expenses.xlsx", mime_type=XLSX_MIME_TYPE),
    name="the input 'workbook'",
    pipe_ref="expenses.append_rows",
)
_METHOD_TEMPLATE_FILE = ComposedTemplateFile(
    file=MethodFileRef(tree_digest="sha256:" + "b" * 64, tree_path="templates/expenses.xlsx"),
    name="templates/expenses.xlsx",
    pipe_ref="expenses.append_rows",
)


def _composition(**overrides: Any) -> DocumentComposition:
    kwargs: dict[str, Any] = {
        "format": DocGenFormat.XLSX,
        "source": DocGenSource.TEMPLATE_FILE,
        "filename": "expenses.xlsx",
        "title": "Expenses",
        "template_file": _INPUT_TEMPLATE_FILE,
        "data": {"expense_rows": [{"description": "Tea", "amount": 7}]},
    }
    kwargs.update(overrides)
    return DocumentComposition(**kwargs)


def _zip_bomb(*, inflated_bytes: int) -> bytes:
    """A zip whose content-types entry declares a hundred bytes and deflates to `inflated_bytes` zeros."""
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    chunk = b"\0" * (1024 * 1024)
    compressed = b"".join(compressor.compress(chunk) for _ in range(inflated_bytes // len(chunk))) + compressor.flush()
    name = b"[Content_Types].xml"
    crc = zlib.crc32(b"x" * 100)
    local_header = struct.pack("<4s5H3L2H", b"PK\x03\x04", 20, 0, 8, 0, 0, crc, len(compressed), 100, len(name), 0) + name
    central_header = struct.pack("<4s6H3L5H2L", b"PK\x01\x02", 20, 20, 0, 8, 0, 0, crc, len(compressed), 100, len(name), 0, 0, 0, 0, 0, 0) + name
    end_record = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 1, 1, len(central_header), len(local_header) + len(compressed), 0)
    return local_header + compressed + central_header + end_record


def _doc_gen_model(*, inputs: list[str]) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="internal",
        name="pipelex-xlsx",
        sdk="openpyxl",
        model_type=ModelType.DOC_GEN,
        model_id="fill-xlsx",
        inputs=inputs,
        outputs=["xlsx"],
        costs={},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )


class TestTemplateInput:
    @pytest.mark.parametrize(
        ("template_file", "expected_name", "expected_desc"),
        [
            (_INPUT_TEMPLATE_FILE, "the input 'workbook'", "the template the input 'workbook' supplies"),
            (_METHOD_TEMPLATE_FILE, "templates/expenses.xlsx", "the template file 'templates/expenses.xlsx'"),
        ],
        ids=["run_input", "method_file"],
    )
    def test_the_job_names_the_template_by_its_origin_and_carries_the_fill(
        self, template_file: ComposedTemplateFile, expected_name: str, expected_desc: str
    ) -> None:
        composition = _composition(template_file=template_file, table_fill=TableFill.APPEND)

        job = composition.make_render_job(template=b"PK workbook")

        assert job.template == b"PK workbook"
        assert job.template_name == expected_name
        assert job.table_fill == TableFill.APPEND
        assert template_file.desc == expected_desc

    def test_the_two_origins_round_trip_through_json_as_the_print_activity_s_payload(self) -> None:
        for template_file, expected_type in ((_INPUT_TEMPLATE_FILE, TemplateInputFile), (_METHOD_TEMPLATE_FILE, MethodFileRef)):
            composition = _composition(template_file=template_file)
            restored = DocumentComposition.model_validate_json(composition.model_dump_json())
            assert restored == composition
            assert restored.template_file is not None
            assert isinstance(restored.template_file.file, expected_type)

    def test_a_run_input_s_template_is_a_read_the_print_authorizes(self) -> None:
        (uri_reference,) = _composition().referenced_uris()
        assert uri_reference.uri == "pipelex-storage://acme/runs/r1/expenses.xlsx"

    def test_a_method_file_template_declares_no_uri_read(self) -> None:
        assert _composition(template_file=_METHOD_TEMPLATE_FILE).referenced_uris() == []

    def test_a_run_input_never_supplies_an_html_template(self) -> None:
        with pytest.raises(ValidationError, match="never an HTML template"):
            ComposedTemplateFile(
                file=TemplateInputFile(input_name="page", url="pipelex-storage://acme/page.html"),
                name="the input 'page'",
                pipe_ref="pages.print",
                render_context=TemplateRenderContext(crate_fingerprint="", concepts_crate={}, working_memory_raw={}),
            )

    def test_the_default_fill_replaces(self) -> None:
        assert _composition().make_render_job(template=b"PK").table_fill == TableFill.REPLACE

    def test_a_composition_of_the_auto_layout_cannot_append(self) -> None:
        with pytest.raises(ValidationError, match="fills no Table of a template file, so it cannot append records to a Table"):
            DocumentComposition(
                format=DocGenFormat.XLSX,
                source=DocGenSource.LAYOUT,
                filename="expenses.xlsx",
                title="Expenses",
                layout=LayoutDocument(title="Expenses", blocks=[]),
                table_fill=TableFill.APPEND,
            )

    def test_a_render_job_of_the_auto_layout_cannot_append(self) -> None:
        with pytest.raises(ValidationError, match="fills no Table of a template file"):
            RenderJob(
                format=DocGenFormat.XLSX,
                source=DocGenSource.LAYOUT,
                filename="expenses.xlsx",
                title="Expenses",
                layout=LayoutDocument(title="Expenses", blocks=[]),
                table_fill=TableFill.APPEND,
            )

    def test_a_render_job_reads_the_fill_as_a_token(self) -> None:
        job = RenderJob.model_validate(
            {"format": "xlsx", "source": "template_file", "filename": "e.xlsx", "title": "E", "template": "UEs=", "table_fill": "append"}
        )
        assert job.table_fill == TableFill.APPEND

    @pytest.mark.parametrize(
        ("inputs", "table_fill", "expected"),
        [
            (["layout", "template_file"], TableFill.REPLACE, True),
            (["layout", "template_file"], TableFill.APPEND, False),
            (["layout", "template_file", TABLE_APPEND_CAPABILITY], TableFill.APPEND, True),
        ],
        ids=["replace_needs_no_declaration", "append_undeclared", "append_declared"],
    )
    def test_an_engine_fills_tables_by_the_capabilities_its_model_declares(self, inputs: list[str], table_fill: TableFill, expected: bool) -> None:
        assert fills_tables(inference_model=_doc_gen_model(inputs=inputs), table_fill=table_fill) is expected

    def test_the_capability_refusal_names_the_fill(self) -> None:
        error = DocGenModelCapabilityError(
            doc_gen_format=DocGenFormat.XLSX,
            source=DocGenSource.TEMPLATE_FILE,
            model="pipelex-xlsx",
            pipe_code="append_rows",
            table_fill=TableFill.APPEND,
        )
        assert "PipeDocGen 'append_rows' asks the engine 'pipelex-xlsx' to append records to a Table" in error.message
        assert 'table_fill = "append"' in error.message
        assert "'table_append'" in error.message
        assert error.problem_params() == {"model": "pipelex-xlsx", "capability": "table_append"}

    @pytest.mark.parametrize(
        ("data", "mime_type", "file_name", "expected"),
        [
            (xlsx_bytes(), DOCX_MIME_TYPE, "report.docx", "xlsx"),
            (docx_bytes(), XLSX_MIME_TYPE, "expenses.xlsx", "docx"),
            (office_package_bytes(main_content_type=PPTX_MAIN_CONTENT_TYPE), None, None, "pptx"),
            (office_package_bytes(main_content_type=None), XLSX_MIME_TYPE, "expenses.xlsx", "zip"),
            (b"%PDF-1.7\n%stub", XLSX_MIME_TYPE, "expenses.xlsx", "pdf"),
            (b"description,amount\n", "text/csv", "expenses.xlsx", "csv"),
            (b"description,amount\n", None, "expenses.XLSX", "xlsx"),
            (b"description,amount\n", None, None, None),
        ],
        ids=[
            "workbook_bytes_beat_a_word_type_and_name",
            "word_bytes_beat_an_excel_type_and_name",
            "deck_from_bytes_alone",
            "zip_without_content_types",
            "pdf_bytes",
            "text_falls_back_to_its_media_type",
            "then_to_its_suffix",
            "nothing_tells",
        ],
    )
    def test_the_bytes_decide_first_then_the_media_type_then_the_suffix(
        self, data: bytes, mime_type: str | None, file_name: str | None, expected: str | None
    ) -> None:
        assert judge_file_format(data=data, mime_type=mime_type, file_name=file_name) == expected

    def test_bytes_that_are_not_a_zip_have_no_office_format(self) -> None:
        assert office_format_of_zip(data=b"%PDF-1.7") is None

    def test_a_main_part_declared_in_single_quotes_is_recognised(self) -> None:
        """XML lets an attribute be quoted either way, so a workbook writing `ContentType='…'` is still a workbook."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as package:
            package.writestr(
                "[Content_Types].xml",
                "<?xml version='1.0' encoding='UTF-8'?>"
                "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
                f"<Override PartName='/xl/workbook.xml' ContentType = '{XLSX_MAIN_CONTENT_TYPE}'/>"
                "</Types>",
            )
        assert office_format_of_zip(data=buffer.getvalue()) == "xlsx"

    def test_a_content_types_entry_that_inflates_past_its_declared_size_is_never_expanded(self) -> None:
        """An entry declaring a few bytes and deflating to many is abandoned after a bounded read, and the file is a bare zip."""
        bomb = _zip_bomb(inflated_bytes=64 * 1024 * 1024)
        tracemalloc.start()
        try:
            judged = office_format_of_zip(data=bomb)
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert judged == ZIP_FORMAT_KEY
        assert peak < 8 * 1024 * 1024
