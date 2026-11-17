import re
from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint


class TestPipeStructureBlueprint:
    def test_valid_single_input_text_compatible_and_structured_output(self):
        blueprint = PipeStructureBlueprint(
            description="Structure the text into a Foo",
            inputs={"draft_text": "native.Text"},
            output="Foo",
        )
        assert blueprint.nb_inputs == 1
        assert blueprint.input_names == ["draft_text"]
        assert blueprint.output == "Foo"

    def test_valid_with_list_output(self):
        blueprint = PipeStructureBlueprint(
            description="Produce a list of Foo",
            inputs={"draft_text": "native.Text"},
            output="Foo[]",
        )
        assert blueprint.output == "Foo[]"

    def test_valid_with_fixed_count_output(self):
        blueprint = PipeStructureBlueprint(
            description="Produce 3 Foo",
            inputs={"draft_text": "native.Text"},
            output="Foo[3]",
        )
        assert blueprint.output == "Foo[3]"

    def test_rejects_native_text_output(self):
        with pytest.raises(ValueError, match="must be a structured concept"):
            PipeStructureBlueprint(
                description="Bad",
                inputs={"draft_text": "native.Text"},
                output="native.Text",
            )

    def test_rejects_bare_text_output(self):
        with pytest.raises(ValueError, match="must be a structured concept"):
            PipeStructureBlueprint(
                description="Bad",
                inputs={"draft_text": "native.Text"},
                output="Text",
            )

    def test_rejects_zero_inputs(self):
        with pytest.raises(ValueError, match="requires exactly one input"):
            PipeStructureBlueprint(
                description="Bad",
                inputs=None,
                output="Foo",
            )

    def test_rejects_multiple_inputs(self):
        with pytest.raises(ValueError, match="requires exactly one input"):
            PipeStructureBlueprint(
                description="Bad",
                inputs={"a": "native.Text", "b": "native.Text"},
                output="Foo",
            )

    @pytest.mark.parametrize("input_spec", ["Text[]", "Text[2]", "native.Text[]", "native.Text[5]"])
    def test_rejects_multiplicity_input(self, input_spec: str):
        """A PipeStructure input carrying multiplicity is rejected at construction time."""
        with pytest.raises(ValueError, match="carries multiplicity"):
            PipeStructureBlueprint(
                description="Bad",
                inputs={"draft_text": input_spec},
                output="Foo",
            )

    def test_accepts_single_text_input(self):
        """A single non-bracketed Text input is accepted."""
        blueprint = PipeStructureBlueprint(
            description="Structure the text into a Foo",
            inputs={"draft_text": "Text"},
            output="Foo",
        )
        assert blueprint.input_names == ["draft_text"]


class TestPipeStructureSheetRangeBlueprint:
    @pytest.mark.parametrize(
        ("sheet_range", "expected"),
        [
            ({}, (None, None)),
            ({"sheet": "Expenses"}, ("Expenses", None)),
            ({"sheet": "Expenses", "header_row": 3}, ("Expenses", 3)),
        ],
        ids=["the-only-sheet", "a-named-sheet", "a-named-sheet-and-header-row"],
    )
    def test_accepted_sheet_ranges(self, sheet_range: dict[str, Any], expected: tuple[str | None, int | None]) -> None:
        blueprint = PipeStructureBlueprint.model_validate(
            {"description": "Read", "inputs": {"expenses": "Document"}, "output": "Expense[]", "sheet_range": sheet_range}
        )

        assert blueprint.sheet_range is not None
        assert (blueprint.sheet_range.sheet, blueprint.sheet_range.header_row) == expected

    @pytest.mark.parametrize(
        ("overrides", "expected_message"),
        [
            ({"table": "Lines", "sheet_range": {}}, "use 'table' or 'sheet_range', not both"),
            ({"sheet_range": {"header_row": 0}}, "greater than or equal to 1"),
            ({"sheet_range": {"header_row": "3"}}, "valid integer"),
            ({"sheet_range": {"header_row": 2.0}}, "valid integer"),
            ({"sheet_range": {"range": "A3:D9"}}, "Extra inputs are not permitted"),
        ],
        ids=["with-table", "row-zero", "row-as-text", "row-as-number", "unknown-field"],
    )
    def test_refused_sheet_ranges(self, overrides: dict[str, Any], expected_message: str) -> None:
        with pytest.raises(ValidationError, match=re.escape(expected_message)):
            PipeStructureBlueprint(description="Read", inputs={"expenses": "Document"}, output="Expense[]", **overrides)
