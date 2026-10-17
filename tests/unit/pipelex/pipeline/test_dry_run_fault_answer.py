import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.core.exceptions import DryRunFailureErrorData
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.errors.error_codes import ErrorCode, first_fault_code
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipe_run.exceptions import DryRunError, DryRunGraphNotProducedError
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error
from pipelex.system.pipe_run_mode import PipeRunMode


def _translate(*, error: Exception) -> None:
    """Raise ``error`` inside the validation translation, which answers what it becomes."""
    with translate_to_validate_bundle_error():
        raise error


def _failure(*, code: ErrorCode, pipe_code: str) -> DryRunFailureErrorData:
    return DryRunFailureErrorData(code=code, pipe_code=pipe_code, domain_code="board", message=f"Pipe '{pipe_code}' failed its dry run")


class TestDryRunFaultAnswer:
    def test_a_dry_run_failing_on_a_fault_of_ours_answers_that_fault(self) -> None:
        """No item is the method's, so validation gives no verdict: it answers the fault, every failure among its items."""
        failures = [
            _failure(code=PipelexErrorCode.STORAGE_UNAVAILABLE, pipe_code="draw"),
            _failure(code=CoreCode.RUNTIME_UNEXPECTED, pipe_code="summarize"),
        ]

        with pytest.raises(DryRunError) as exc_info:
            _translate(error=DryRunError("two pipes failed their dry run", failures=failures))

        assert not isinstance(exc_info.value, ValidateBundleError)
        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        # A verdict `no` comes before a retryable one, so no client retries what someone must fix.
        assert problem.code == CoreCode.RUNTIME_UNEXPECTED
        assert problem.code != CoreCode.METHOD_INVALID
        assert problem.errors is not None
        assert [(item.code, item.location.pipe if item.location else None) for item in problem.errors] == [
            (PipelexErrorCode.STORAGE_UNAVAILABLE, "draw"),
            (CoreCode.RUNTIME_UNEXPECTED, "summarize"),
        ]

    def test_one_failure_of_the_method_makes_the_dry_run_an_invalid_verdict(self) -> None:
        failures = [
            _failure(code=CoreCode.RUNTIME_UNEXPECTED, pipe_code="summarize"),
            _failure(code=CoreCode.METHOD_WIRING_INVALID, pipe_code="analyze"),
        ]

        with pytest.raises(ValidateBundleError) as exc_info:
            _translate(error=DryRunError("two pipes failed their dry run", failures=failures))

        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_INVALID
        assert problem.effective_domain == "method"
        assert problem.errors is not None
        # Every item rides the verdict, each with its own code.
        assert [item.code for item in problem.errors] == [CoreCode.RUNTIME_UNEXPECTED, CoreCode.METHOD_WIRING_INVALID]

    def test_a_dry_run_that_produced_no_graph_is_a_fault_of_ours(self) -> None:
        with pytest.raises(DryRunGraphNotProducedError) as exc_info:
            _translate(error=DryRunGraphNotProducedError("the dry run produced no graph"))

        assert exc_info.value.to_problem(view=ProblemView.CALLER).code == CoreCode.RUNTIME_UNEXPECTED

    def test_a_pipe_run_failing_on_a_fault_of_ours_is_no_verdict(self) -> None:
        with pytest.raises(PipeRunError) as exc_info:
            _translate(error=PipeRunError(message="an invariant broke", run_mode=PipeRunMode.DRY, pipe_code="route"))

        assert not isinstance(exc_info.value, ValidateBundleError)
        assert exc_info.value.to_problem(view=ProblemView.CALLER).code == CoreCode.RUNTIME_UNEXPECTED

    def test_a_pipe_run_failing_on_the_methods_fault_is_a_verdict(self) -> None:
        with pytest.raises(ValidateBundleError) as exc_info:
            _translate(
                error=PipeRunError(message="unwired", run_mode=PipeRunMode.DRY, pipe_code="route").with_error_code(CoreCode.METHOD_WIRING_INVALID)
            )

        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_INVALID
        assert problem.errors is not None
        (item,) = problem.errors
        assert item.code == CoreCode.METHOD_WIRING_INVALID
        assert item.location is not None
        assert item.location.pipe == "route"

    @pytest.mark.parametrize(
        ("codes", "expected"),
        [
            ([CoreCode.PROVIDER_RATE_LIMITED, CoreCode.RUNTIME_UNEXPECTED], CoreCode.RUNTIME_UNEXPECTED),
            ([CoreCode.RUNTIME_UNEXPECTED, CoreCode.RUNTIME_MISCONFIGURED], CoreCode.RUNTIME_MISCONFIGURED),
            ([CoreCode.INPUT_INVALID, CoreCode.AUTH_FORBIDDEN, CoreCode.RUNTIME_UNEXPECTED], CoreCode.AUTH_FORBIDDEN),
            ([CoreCode.RUNTIME_UNEXPECTED, CoreCode.INPUT_INVALID], CoreCode.INPUT_INVALID),
            ([CoreCode.ACCOUNT_RATE_LIMITED, CoreCode.PROVIDER_RATE_LIMITED], CoreCode.ACCOUNT_RATE_LIMITED),
            ([CoreCode.PROVIDER_RATE_LIMITED, PipelexErrorCode.STORAGE_UNAVAILABLE], CoreCode.PROVIDER_RATE_LIMITED),
            ([], None),
        ],
        ids=[
            "no_before_retryable",
            "operator_before_runtime",
            "account_before_input",
            "input_before_runtime",
            "account_before_runtime",
            "first_given",
            "none",
        ],
    )
    def test_the_answer_takes_the_first_fault_code(self, codes: list[ErrorCode], expected: ErrorCode | None) -> None:
        """A verdict `no` before a retryable one, then the operator's, the account's, the input's, the runtime's, then the first given."""
        assert first_fault_code(codes=codes) == expected
