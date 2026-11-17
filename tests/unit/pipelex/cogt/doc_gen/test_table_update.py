"""The `update` fill and the sheet range as the document engine contract carries them: their fields and their capabilities."""

from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.cogt.doc_gen.doc_gen_engine import fills_sheet_ranges, fills_tables
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.document_composition import ComposedTemplateFile, DocumentComposition, TemplateInputFile
from pipelex.cogt.doc_gen.exceptions import DocGenModelCapabilityError
from pipelex.cogt.doc_gen.layout_tree import LayoutDocument
from pipelex.cogt.doc_gen.render_job import RenderJob
from pipelex.cogt.doc_gen.sheet_range import SheetRangeFill
from pipelex.cogt.doc_gen.table_fill import (
    SHEET_RANGE_CAPABILITY,
    TABLE_APPEND_CAPABILITY,
    TABLE_UPDATE_CAPABILITY,
    CellPolicy,
    TableFill,
    sheet_range_refusal,
    table_match_refusal,
)
from pipelex.cogt.doc_gen.template_check import TemplateCheckRequest
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from tests.helpers.office_files import XLSX_MIME_TYPE

_INPUT_TEMPLATE_FILE = ComposedTemplateFile(
    file=TemplateInputFile(input_name="workbook", url="pipelex-storage://acme/runs/r1/expenses.xlsx", mime_type=XLSX_MIME_TYPE),
    name="the input 'workbook'",
    pipe_ref="expenses.complete_rows",
)

_UPDATE_BY_KEY: dict[str, Any] = {"table_fill": TableFill.UPDATE, "match_on": ["invoice_number"], "cells": CellPolicy.FILL_EMPTY}
_UPDATE_BY_ROW: dict[str, Any] = {"table_fill": TableFill.UPDATE, "match_row": "row", "cells": CellPolicy.OVERWRITE}


def _composition(**overrides: Any) -> DocumentComposition:
    kwargs: dict[str, Any] = {
        "format": DocGenFormat.XLSX,
        "source": DocGenSource.TEMPLATE_FILE,
        "filename": "expenses.xlsx",
        "title": "Expenses",
        "template_file": _INPUT_TEMPLATE_FILE,
        "data": {"completions": [{"invoice_number": "INV-1", "category": None}]},
    }
    kwargs.update(overrides)
    return DocumentComposition(**kwargs)


def _render_job(**overrides: Any) -> RenderJob:
    kwargs: dict[str, Any] = {
        "format": DocGenFormat.XLSX,
        "source": DocGenSource.TEMPLATE_FILE,
        "filename": "expenses.xlsx",
        "title": "Expenses",
        "template": b"PK",
    }
    kwargs.update(overrides)
    return RenderJob(**kwargs)


def _check_request(**overrides: Any) -> TemplateCheckRequest:
    kwargs: dict[str, Any] = {"format": DocGenFormat.XLSX, "template": b"PK", "template_name": "the input 'workbook'", "inputs": {}}
    kwargs.update(overrides)
    return TemplateCheckRequest(**kwargs)


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


class TestTableUpdate:
    @pytest.mark.parametrize("fields", [_UPDATE_BY_KEY, _UPDATE_BY_ROW], ids=["by_key", "by_row"])
    def test_the_composition_hands_the_job_its_matching_fields_and_cell_policy(self, fields: dict[str, Any]) -> None:
        job = _composition(**fields).make_render_job(template=b"PK workbook")

        assert job.table_fill == TableFill.UPDATE
        assert job.match_on == fields.get("match_on")
        assert job.match_row == fields.get("match_row")
        assert job.cells == fields["cells"]

    def test_an_update_composition_round_trips_through_json_as_the_print_activity_s_payload(self) -> None:
        composition = _composition(**_UPDATE_BY_KEY)
        assert DocumentComposition.model_validate_json(composition.model_dump_json()) == composition

    def test_a_render_job_reads_the_update_as_tokens(self) -> None:
        job = RenderJob.model_validate(
            {
                "format": "xlsx",
                "source": "template_file",
                "filename": "e.xlsx",
                "title": "E",
                "template": "UEs=",
                "table_fill": "update",
                "match_row": "row",
                "cells": "fill_empty",
            }
        )
        assert job.table_fill == TableFill.UPDATE
        assert job.cells == CellPolicy.FILL_EMPTY

    def test_any_other_fill_carries_no_matching_field(self) -> None:
        job = _render_job(table_fill=TableFill.APPEND)
        assert (job.match_on, job.match_row, job.cells) == (None, None, None)

    @pytest.mark.parametrize(
        ("fields", "expected_message"),
        [
            ({"table_fill": TableFill.UPDATE, "cells": CellPolicy.FILL_EMPTY}, "by exactly one of match_on and match_row"),
            ({**_UPDATE_BY_KEY, "match_row": "row"}, "by exactly one of match_on and match_row"),
            ({**_UPDATE_BY_KEY, "match_on": []}, "names at least one field"),
            ({**_UPDATE_BY_KEY, "match_on": ["invoice_number", "invoice_number"]}, "names each field once"),
            ({"table_fill": TableFill.UPDATE, "match_on": ["invoice_number"]}, "carries its cell policy, cells"),
            ({"table_fill": TableFill.APPEND, "match_on": ["invoice_number"]}, "its fill 'append' matches no row, so it carries no match_on"),
            ({"table_fill": TableFill.REPLACE, "match_row": "row", "cells": CellPolicy.OVERWRITE}, "carries no match_row, cells"),
        ],
        ids=["no_match", "both_matches", "empty_key", "repeated_key", "no_cell_policy", "key_on_append", "row_and_cells_on_replace"],
    )
    def test_the_job_the_composition_and_the_check_request_refuse_fields_that_do_not_fit_the_fill(
        self, fields: dict[str, Any], expected_message: str
    ) -> None:
        refusal = table_match_refusal(
            table_fill=fields["table_fill"], match_on=fields.get("match_on"), match_row=fields.get("match_row"), cells=fields.get("cells")
        )
        assert refusal is not None
        assert expected_message in refusal
        with pytest.raises(ValidationError, match=expected_message):
            _render_job(**fields)
        with pytest.raises(ValidationError, match=expected_message):
            _composition(**fields)
        with pytest.raises(ValidationError, match=expected_message):
            _check_request(**fields)

    def test_a_render_job_of_the_auto_layout_cannot_update(self) -> None:
        with pytest.raises(ValidationError, match="fills no Table of a template file, so it cannot update a Table's rows with records"):
            RenderJob(
                format=DocGenFormat.XLSX,
                source=DocGenSource.LAYOUT,
                filename="expenses.xlsx",
                title="Expenses",
                layout=LayoutDocument(title="Expenses", blocks=[]),
                **_UPDATE_BY_KEY,
            )

    def test_the_check_request_carries_the_update(self) -> None:
        request = _check_request(**_UPDATE_BY_ROW)
        assert (request.table_fill, request.match_row, request.cells) == (TableFill.UPDATE, "row", CellPolicy.OVERWRITE)
        assert _check_request().table_fill == TableFill.REPLACE

    @pytest.mark.parametrize(
        ("inputs", "expected"),
        [
            (["layout", "template_file"], False),
            (["layout", "template_file", TABLE_APPEND_CAPABILITY], False),
            (["layout", "template_file", TABLE_UPDATE_CAPABILITY], True),
        ],
        ids=["undeclared", "append_is_not_update", "declared"],
    )
    def test_an_engine_updates_only_when_its_model_declares_it(self, inputs: list[str], expected: bool) -> None:
        assert fills_tables(inference_model=_doc_gen_model(inputs=inputs), table_fill=TableFill.UPDATE) is expected

    def test_the_capability_refusal_names_the_update(self) -> None:
        error = DocGenModelCapabilityError(
            doc_gen_format=DocGenFormat.XLSX,
            source=DocGenSource.TEMPLATE_FILE,
            model="pipelex-xlsx",
            pipe_code="complete_rows",
            table_fill=TableFill.UPDATE,
        )
        assert "PipeDocGen 'complete_rows' asks the engine 'pipelex-xlsx' to update a Table's rows with records" in error.message
        assert 'table_fill = "update"' in error.message
        assert "'table_update'" in error.message
        assert error.problem_params() == {"model": "pipelex-xlsx", "capability": "table_update"}


_SHEET_RANGE = SheetRangeFill(list="completions", sheet="Expenses", header_row=3)


class TestSheetRangeContract:
    @pytest.mark.parametrize("fields", [{"table_fill": TableFill.APPEND}, _UPDATE_BY_ROW], ids=["append", "update"])
    def test_the_composition_hands_the_job_its_sheet_range(self, fields: dict[str, Any]) -> None:
        composition = _composition(sheet_range=_SHEET_RANGE, **fields)
        job = composition.make_render_job(template=b"PK")

        assert job.sheet_range == _SHEET_RANGE
        assert DocumentComposition.model_validate_json(composition.model_dump_json()).sheet_range == _SHEET_RANGE
        assert _check_request(sheet_range=_SHEET_RANGE, **fields).sheet_range == _SHEET_RANGE

    def test_the_job_the_composition_and_the_check_request_refuse_a_sheet_range_under_replace(self) -> None:
        expected_message = "its fill 'replace' fills Tables only, so it carries no sheet_range"
        assert sheet_range_refusal(table_fill=TableFill.REPLACE, sheet_range=_SHEET_RANGE) == expected_message
        with pytest.raises(ValidationError, match=expected_message):
            _render_job(sheet_range=_SHEET_RANGE)
        with pytest.raises(ValidationError, match=expected_message):
            _composition(sheet_range=_SHEET_RANGE)
        with pytest.raises(ValidationError, match=expected_message):
            _check_request(sheet_range=_SHEET_RANGE)

    def test_a_sheet_range_fill_names_a_list(self) -> None:
        with pytest.raises(ValidationError):
            SheetRangeFill(list="")

    @pytest.mark.parametrize(
        ("inputs", "expected"),
        [
            (["layout", "template_file", TABLE_APPEND_CAPABILITY, TABLE_UPDATE_CAPABILITY], False),
            (["layout", "template_file", TABLE_APPEND_CAPABILITY, SHEET_RANGE_CAPABILITY], True),
        ],
        ids=["undeclared", "declared"],
    )
    def test_an_engine_fills_sheet_ranges_only_when_its_model_declares_it(self, inputs: list[str], expected: bool) -> None:
        assert fills_sheet_ranges(inference_model=_doc_gen_model(inputs=inputs)) is expected

    def test_the_capability_refusal_names_the_sheet_range(self) -> None:
        error = DocGenModelCapabilityError(
            doc_gen_format=DocGenFormat.XLSX,
            source=DocGenSource.TEMPLATE_FILE,
            model="pipelex-xlsx",
            pipe_code="complete_rows",
            table_fill=TableFill.APPEND,
            fills_sheet_range=True,
        )
        assert "PipeDocGen 'complete_rows' asks the engine 'pipelex-xlsx' to fill a range on a sheet holding no Excel Table" in error.message
        assert "'sheet_range'" in error.message
        assert error.problem_params() == {"model": "pipelex-xlsx", "capability": "sheet_range"}
