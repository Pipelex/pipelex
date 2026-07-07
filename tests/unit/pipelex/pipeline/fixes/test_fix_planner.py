"""Unit tests for the fix planner — enriched error data in, ``SuggestedFix`` out.

The planner is a pure translation keyed on ``error_type`` + structured fields (never
message strings). It only fires when the enriched ``expected_output_ref`` is present —
which only the ``PipeSequence`` raise sites set — so ``INADEQUATE_OUTPUT_*`` errors from
PipeParallel / PipeCondition / operator pipes are suppressed structurally.
"""

from pipelex.core.exceptions import PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.pipeline.fixes.planner import plan_fix_for_pipe_validation_error
from pipelex.suggested_fix import FixOpKind, FixSafety


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


class TestFixPlanner:
    def test_concept_mismatch_yields_match_sequence_output_fix(self) -> None:
        """An enriched INADEQUATE_OUTPUT_CONCEPT yields a SAFE set_key fix on the pipe's output."""
        fix = plan_fix_for_pipe_validation_error(_error_data(error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT))
        assert fix is not None
        assert fix.fix_code == "match-sequence-output"
        assert fix.safety == FixSafety.SAFE
        assert fix.source == "main.mthds"
        assert len(fix.ops) == 1
        the_op = fix.ops[0]
        assert the_op.kind == FixOpKind.SET_KEY
        assert the_op.table_path == ["pipe", "list_ideas"]
        assert the_op.key == "output"
        assert the_op.value == "Idea[]"

    def test_multiplicity_mismatch_yields_fix_with_expected_ref_value(self) -> None:
        """An enriched INADEQUATE_OUTPUT_MULTIPLICITY yields the same fix, carrying the expected ref."""
        fix = plan_fix_for_pipe_validation_error(
            _error_data(error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY, expected_output_ref="Idea[3]")
        )
        assert fix is not None
        assert fix.fix_code == "match-sequence-output"
        assert fix.ops[0].value == "Idea[3]"

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
