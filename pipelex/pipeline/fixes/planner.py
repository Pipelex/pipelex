"""Fix planner — translates enriched validation error data into ``SuggestedFix`` payloads.

Pure functions keyed strictly on ``error_type`` + structured fields, never message strings.
The planner runs inside report assembly (``build_validation_error_items``), so every consumer
of the validation report — CLI, API, MCP — sees fixes with zero extra plumbing.
"""

from pipelex.core.exceptions import PipesAndConceptValidationErrorData
from pipelex.suggested_fix import FixOp, FixOpKind, FixSafety, SuggestedFix

MATCH_SEQUENCE_OUTPUT_FIX_CODE = "match-sequence-output"


def plan_fix_for_pipe_validation_error(error_data: PipesAndConceptValidationErrorData) -> SuggestedFix | None:
    """Derive a suggested fix from one pipe-validation error data, or ``None`` when not fixable.

    ``match-sequence-output``: an ``INADEQUATE_OUTPUT_CONCEPT`` / ``INADEQUATE_OUTPUT_MULTIPLICITY``
    carrying the enriched ``expected_output_ref`` becomes a ``set_key`` of the pipe's ``output``.
    Only the ``PipeSequence`` raise sites set ``expected_output_ref`` — PipeParallel / PipeCondition /
    operator pipes raise the same error types but their output choice is ambiguous, so their errors
    carry no expected ref and are suppressed here structurally.
    """
    if not error_data.error_type.is_inadequate_output:
        return None
    if error_data.expected_output_ref is None or error_data.pipe_code is None:
        return None
    return SuggestedFix(
        fix_code=MATCH_SEQUENCE_OUTPUT_FIX_CODE,
        description=f"Set output of pipe '{error_data.pipe_code}' to '{error_data.expected_output_ref}' to match its last step",
        safety=FixSafety.SAFE,
        source=error_data.source,
        ops=[
            FixOp(
                kind=FixOpKind.SET_KEY,
                table_path=["pipe", error_data.pipe_code],
                key="output",
                value=error_data.expected_output_ref,
            ),
        ],
    )
