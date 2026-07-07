"""Unit test for the convergence loop's no-progress bail — it exits loudly, never spins.

The validator is stubbed to keep raising the same enriched error whose fix op targets a
pipe table absent from the file (the synthetic-pipe case): the applier skips the op, the
next iteration proposes the same fix fingerprint, and the loop bails with the reason
reported instead of burning through max_iterations.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.core.exceptions import PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.fixes.fix_loop import fix_bundle_file

_MINIMAL_MTHDS = """domain = "seqfix_bail"
main_pipe = "declared_pipe"

[pipe.declared_pipe]
type = "PipeLLM"
description = "A pipe that exists in the file."
inputs = { topic = "Text" }
output = "Text"
prompt = "Write about $topic"
"""


def _synthetic_pipe_error() -> ValidateBundleError:
    """An enriched output-mismatch error on a pipe with no TOML table in the file."""
    return ValidateBundleError(
        message="Pipe validation failed",
        pipe_validation_errors=[
            PipesAndConceptValidationErrorData(
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY,
                domain_code="seqfix_bail",
                pipe_code="synthetic_pipe_not_in_file",
                message="output mismatch",
                field_path="",
                expected_output_ref="Text[]",
            ),
        ],
    )


@pytest.mark.asyncio(loop_scope="class")
class TestFixLoopBail:
    async def test_repeated_fingerprint_bails_loudly(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """The same fix fingerprint proposed twice ends the loop with a reported bail reason."""
        bundle_path = tmp_path / "bail.mthds"
        bundle_path.write_text(_MINIMAL_MTHDS, encoding="utf-8")
        validate_mock = mocker.patch(
            "pipelex.pipeline.fixes.fix_loop.validate_bundle",
            side_effect=_synthetic_pipe_error(),
        )

        result = await fix_bundle_file(bundle_path, max_iterations=5)

        assert result.is_valid is False
        assert result.bail_reason is not None
        assert "fingerprint" in result.bail_reason
        # One apply round happened (all ops skipped), then the repeat was detected: the loop
        # validated twice, not five times.
        assert result.iterations == 1
        assert result.fixes_applied == []
        assert validate_mock.await_count == 2
        assert [item.error_type for item in result.remaining_errors] == [PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY]
        # The file was never touched: the op's target table does not exist.
        assert bundle_path.read_text(encoding="utf-8") == _MINIMAL_MTHDS
