"""Unit tests for the fix planner — enriched error data in, ``SuggestedFix`` out.

The planner is a pure translation keyed on ``error_type`` + structured fields (never
message strings). Each rule only fires when its enrichment is present — set only at the
raise sites that know the correct value — so the same error types raised elsewhere are
suppressed structurally: ``expected_output_ref`` for ``match-sequence-output`` (PipeSequence
raise sites only), ``expected_inputs``/``declared_inputs`` for ``sync-controller-inputs``
(controller input-drift sites only).
"""

import pytest

from pipelex.core.exceptions import PipesAndConceptValidationErrorData
from pipelex.pipeline.fixes.planner import KNOWN_FIX_CODES, RENAME_MODEL_FIX_CODE, plan_fix_for_pipe_validation_error
from pipelex.suggested_fix import DeleteKeyOp, EnsureTableOp, FixSafety, RemapValueOp, SetKeyOp
from pipelex.validation_error_types import PipeValidationErrorType

# The inputs table of the pipe every input-drift case below is built around.
_INPUTS_TABLE_PATH = ["pipe", "make_summary", "inputs"]


def _error_data(
    *,
    error_type: PipeValidationErrorType,
    pipe_code: str | None = "list_ideas",
    expected_output_ref: str | None = "Idea[]",
    source: str | None = "main.mthds",
) -> PipesAndConceptValidationErrorData:
    return PipesAndConceptValidationErrorData(
        error_type=error_type,
        domain_code="testapp",
        source=source,
        pipe_code=pipe_code,
        message="output mismatch",
        field_path="",
        expected_output_ref=expected_output_ref,
    )


def _input_drift_error_data(
    *,
    error_type: PipeValidationErrorType = PipeValidationErrorType.MISSING_INPUT_VARIABLE,
    pipe_code: str | None = "make_summary",
    expected_inputs: dict[str, str] | None = None,
    declared_inputs: dict[str, str] | None = None,
    source: str | None = "main.mthds",
) -> PipesAndConceptValidationErrorData:
    return PipesAndConceptValidationErrorData(
        error_type=error_type,
        domain_code="testapp",
        source=source,
        pipe_code=pipe_code,
        message="input drift",
        field_path="",
        expected_inputs=expected_inputs,
        declared_inputs=declared_inputs,
    )


def _unknown_model_error_data(
    *,
    suggestions: list[str] | None,
    field_name: str | None = "model",
    model_reference: str | None = "@best-sonet",
) -> PipesAndConceptValidationErrorData:
    return PipesAndConceptValidationErrorData(
        error_type=PipeValidationErrorType.UNKNOWN_MODEL,
        domain_code="tide_tables",
        source="main.mthds",
        pipe_code="write_tide_note",
        field_name=field_name,
        message="unknown model",
        field_path="pipe.write_tide_note.model",
        model_reference=model_reference,
        model_type="llm",
        suggestions=suggestions,
    )


class TestFixPlanner:
    def test_concept_mismatch_yields_match_sequence_output_fix(self) -> None:
        """An enriched INADEQUATE_OUTPUT_CONCEPT yields a SAFE set_key fix on the pipe's output."""
        fix = plan_fix_for_pipe_validation_error(_error_data(error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT))
        assert fix is not None
        assert fix.fix_code == "match-sequence-output"
        assert fix.safety == FixSafety.SAFE
        assert fix.source == "main.mthds"
        assert fix.ops == [SetKeyOp(table_path=["pipe", "list_ideas"], key="output", value="Idea[]")]

    def test_multiplicity_mismatch_yields_fix_with_expected_ref_value(self) -> None:
        """An enriched INADEQUATE_OUTPUT_MULTIPLICITY yields the same fix, carrying the expected ref."""
        fix = plan_fix_for_pipe_validation_error(
            _error_data(error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY, expected_output_ref="Idea[3]")
        )
        assert fix is not None
        assert fix.fix_code == "match-sequence-output"
        assert fix.ops == [SetKeyOp(table_path=["pipe", "list_ideas"], key="output", value="Idea[3]")]

    def test_missing_expected_ref_yields_none(self) -> None:
        """No enriched expected ref (PipeParallel / PipeCondition / operator raise sites) → no fix."""
        fix = plan_fix_for_pipe_validation_error(_error_data(error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT, expected_output_ref=None))
        assert fix is None

    def test_missing_pipe_code_yields_none(self) -> None:
        """Without a pipe locator there is no TOML table to patch → no fix."""
        fix = plan_fix_for_pipe_validation_error(_error_data(error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT, pipe_code=None))
        assert fix is None

    def test_unrelated_error_type_yields_none(self) -> None:
        """The planner is keyed on error_type: other types never produce this fix."""
        fix = plan_fix_for_pipe_validation_error(_error_data(error_type=PipeValidationErrorType.UNRESOLVED_CONCEPT))
        assert fix is None

    def test_missing_source_still_yields_fix(self) -> None:
        """A single-file validation has no source on the error data; the fix still applies (source=None)."""
        fix = plan_fix_for_pipe_validation_error(_error_data(error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT, source=None))
        assert fix is not None
        assert fix.source is None

    @pytest.mark.parametrize(
        "error_type",
        [
            PipeValidationErrorType.MISSING_INPUT_VARIABLE,
            PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
            PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
        ],
    )
    def test_input_drift_yields_sync_controller_inputs_fix(self, error_type: PipeValidationErrorType) -> None:
        """Each enriched input-drift error type yields one SAFE sync-controller-inputs fix."""
        fix = plan_fix_for_pipe_validation_error(
            _input_drift_error_data(
                error_type=error_type,
                expected_inputs={"text": "Text"},
                declared_inputs={"text": "Number"},
            )
        )
        assert fix is not None
        assert fix.fix_code == "sync-controller-inputs"
        assert fix.safety == FixSafety.SAFE
        assert fix.source == "main.mthds"
        assert fix.ops == [SetKeyOp(table_path=_INPUTS_TABLE_PATH, key="text", value="Text")]

    def test_input_drift_diff_adds_updates_and_deletes(self) -> None:
        """The fix is a diff: set_key for added/changed variables, delete_key for extraneous ones."""
        fix = plan_fix_for_pipe_validation_error(
            _input_drift_error_data(
                expected_inputs={"text": "Text", "doc": "Doc"},
                declared_inputs={"text": "Number", "note": "Text"},
            )
        )
        assert fix is not None
        assert fix.ops == [
            SetKeyOp(table_path=_INPUTS_TABLE_PATH, key="text", value="Text"),
            SetKeyOp(table_path=_INPUTS_TABLE_PATH, key="doc", value="Doc"),
            DeleteKeyOp(table_path=_INPUTS_TABLE_PATH, key="note"),
        ]
        for var_name in ("text", "doc", "note"):
            assert var_name in fix.description

    def test_matching_declared_variable_gets_no_op(self) -> None:
        """A declared variable whose rendered ref already matches is left untouched."""
        fix = plan_fix_for_pipe_validation_error(
            _input_drift_error_data(
                error_type=PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
                expected_inputs={"doc": "Text?", "note": "Text"},
                declared_inputs={"doc": "Text?"},
            )
        )
        assert fix is not None
        assert fix.ops == [SetKeyOp(table_path=_INPUTS_TABLE_PATH, key="note", value="Text")]

    def test_no_declared_inputs_ensures_table_then_sets_each_key(self) -> None:
        """The same ops create a missing table or preserve an explicitly empty block table."""
        fix = plan_fix_for_pipe_validation_error(
            _input_drift_error_data(
                expected_inputs={"text": "Text", "doc": "Doc?"},
                declared_inputs={},
            )
        )
        assert fix is not None
        assert fix.ops == [
            EnsureTableOp(table_path=_INPUTS_TABLE_PATH),
            SetKeyOp(table_path=_INPUTS_TABLE_PATH, key="text", value="Text"),
            SetKeyOp(table_path=_INPUTS_TABLE_PATH, key="doc", value="Doc?"),
        ]

    def test_equal_mappings_yield_none(self) -> None:
        """An empty diff (renderings already agree) must not produce a no-op fix."""
        fix = plan_fix_for_pipe_validation_error(
            _input_drift_error_data(
                error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
                expected_inputs={"text": "Text"},
                declared_inputs={"text": "Text"},
            )
        )
        assert fix is None

    def test_input_drift_without_expected_inputs_yields_none(self) -> None:
        """No enrichment (operator raise sites) → no fix."""
        fix = plan_fix_for_pipe_validation_error(_input_drift_error_data(expected_inputs=None, declared_inputs={"text": "Text"}))
        assert fix is None

    def test_input_drift_without_declared_inputs_yields_none(self) -> None:
        """Without the declared mapping the planner cannot diff → no fix."""
        fix = plan_fix_for_pipe_validation_error(_input_drift_error_data(expected_inputs={"text": "Text"}, declared_inputs=None))
        assert fix is None

    def test_input_drift_without_pipe_code_yields_none(self) -> None:
        """Without a pipe locator there is no TOML table to patch → no fix."""
        fix = plan_fix_for_pipe_validation_error(_input_drift_error_data(pipe_code=None, expected_inputs={"text": "Text"}, declared_inputs={}))
        assert fix is None

    def test_unknown_model_with_one_suggestion_yields_rename_model_fix(self) -> None:
        """One close match in the deck is the one obvious correction: remap the field from the reference as written."""
        fix = plan_fix_for_pipe_validation_error(_unknown_model_error_data(suggestions=["@best-gpt"]))
        assert fix is not None
        assert fix.fix_code == RENAME_MODEL_FIX_CODE
        assert fix.safety == FixSafety.UNSAFE
        assert RENAME_MODEL_FIX_CODE not in KNOWN_FIX_CODES, "an unsafe code is never selectable: the fix loop would skip it"
        assert fix.source == "main.mthds"
        assert fix.ops == [RemapValueOp(table_path=["pipe", "write_tide_note"], key="model", mapping={"@best-sonet": "@best-gpt"})]
        assert "'@best-sonet'" in fix.description
        assert "'@best-gpt'" in fix.description

    def test_unknown_model_fix_rewrites_the_field_that_named_it(self) -> None:
        fix = plan_fix_for_pipe_validation_error(_unknown_model_error_data(suggestions=["@best-gpt"], field_name="model_to_structure"))
        assert fix is not None
        assert fix.ops == [RemapValueOp(table_path=["pipe", "write_tide_note"], key="model_to_structure", mapping={"@best-sonet": "@best-gpt"})]

    @pytest.mark.parametrize("suggestions", [None, [], ["$writing-factual", "$writing-creative"]])
    def test_unknown_model_without_exactly_one_suggestion_yields_none(self, suggestions: list[str] | None) -> None:
        """No match leaves nothing to write, and several leave the choice to the author."""
        assert plan_fix_for_pipe_validation_error(_unknown_model_error_data(suggestions=suggestions)) is None

    def test_unknown_model_without_its_locators_yields_none(self) -> None:
        assert plan_fix_for_pipe_validation_error(_unknown_model_error_data(suggestions=["@best-gpt"], field_name=None)) is None
        assert plan_fix_for_pipe_validation_error(_unknown_model_error_data(suggestions=["@best-gpt"], model_reference=None)) is None

    def test_uncoded_pipe_error_yields_none(self) -> None:
        """A located refusal with no closed code (the cascade's general arm) has no fix to plan."""
        error_data = PipesAndConceptValidationErrorData(pipe_code="write_tide_note", message="refused", field_path="")
        assert plan_fix_for_pipe_validation_error(error_data) is None
