"""What an inference failure built with a category and no code reports.

The classification picks a code with every category it reads, and a worker raising a failure itself chooses one. A
failure a worker or a plugin builds by hand with a category alone still reports a code, and its domain and retry
verdict are that code's: the category's own (``InferenceErrorCategory.default_error_code``), unless a code was chosen
or a cause carries one, so that a transient failure, which the run repeats, never reports a failure no retry clears.
"""

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.errors.error_code_declaration import InheritsCause
from pipelex.errors.error_codes import ErrorCode
from pipelex.pipe_run.located_failure import find_root_fault
from tests.unit.pipelex.cogt.test_data import ExceptionTestData


class _CodedCauseError(PipelexError):
    """Test-only cause carrying a code of its own."""

    error_code = CoreCode.INPUT_TOO_LARGE


class _WrapperError(PipelexError):
    """Test-only wrapper that takes its cause's code, as the pipe and run wrappers do."""

    error_code = InheritsCause(fallback=CoreCode.RUNTIME_UNEXPECTED)


class TestInferenceErrorDomain:
    @pytest.mark.parametrize(
        ("_topic", "category", "expected_code", "expected_domain", "expected_retryable"),
        ExceptionTestData.CATEGORY_CODE_CASES,
    )
    def test_a_category_alone_reports_its_code(
        self,
        _topic: str,
        category: InferenceErrorCategory,
        expected_code: ErrorCode,
        expected_domain: ErrorDomain,
        expected_retryable: bool,
    ) -> None:
        """A failure naming only a category reports the category's code, and that code's domain and retry verdict."""
        report = LLMCompletionError("boom", error_category=category).to_error_report()

        assert report.code == expected_code
        assert report.error_domain == expected_domain
        assert report.retryable is expected_retryable
        assert report.error_category == category

    def test_category_code_cases_cover_every_category(self) -> None:
        """The parametrized table is exhaustive — a new category cannot slip in undecided."""
        covered = {category for _topic, category, _code, _domain, _retryable in ExceptionTestData.CATEGORY_CODE_CASES}
        assert covered == set(InferenceErrorCategory)

    def test_a_retryable_category_never_reports_a_code_no_retry_clears(self) -> None:
        """The run repeats a call whose category is retryable, so the report of one built with no code must invite a retry too."""
        for category in InferenceErrorCategory:
            report = LLMCompletionError("boom", error_category=category).to_error_report()
            if category.is_retryable:
                assert report.retryable is True, category

    def test_a_chosen_code_beats_the_category(self) -> None:
        """The raise site that chose a code knows more than the category."""
        error = LLMCompletionError("rate limited", error_category=InferenceErrorCategory.TRANSIENT).with_error_code(CoreCode.PROVIDER_RATE_LIMITED)

        assert error.resolve_error_code() == CoreCode.PROVIDER_RATE_LIMITED

    def test_a_coded_cause_beats_the_category(self) -> None:
        """A failure class takes its cause's code, and the category is only for a failure whose chain carries none."""
        error = LLMCompletionError("wrapped", error_category=InferenceErrorCategory.TRANSIENT)
        error.__cause__ = _CodedCauseError("too large")

        assert error.resolve_error_code() == CoreCode.INPUT_TOO_LARGE

    def test_a_cause_that_is_no_pipelex_error_leaves_the_category_its_say(self) -> None:
        """An SDK exception under the failure carries no code, so the category still names one."""
        error = LLMCompletionError("connection reset", error_category=InferenceErrorCategory.TRANSIENT)
        error.__cause__ = ConnectionResetError("reset by peer")

        assert error.resolve_error_code() == CoreCode.PROVIDER_UNAVAILABLE

    def test_a_wrapper_reports_the_category_s_code(self) -> None:
        """The pipe and run wrappers take their cause's code, so a transient failure stays retryable through them."""
        failure = LLMCompletionError("connection reset", error_category=InferenceErrorCategory.TRANSIENT)
        wrapper = _WrapperError("Pipe 'greet' failed")
        wrapper.__cause__ = failure

        report = wrapper.to_error_report()

        assert report.code == CoreCode.PROVIDER_UNAVAILABLE
        assert report.retryable is True

    def test_a_cyclic_pair_of_category_failures_reports_without_recursing(self) -> None:
        """Two failures chained to each other report the category's code, under a wrapper too, where the walk of each recursed."""
        outer = LLMCompletionError("connection reset", error_category=InferenceErrorCategory.TRANSIENT)
        inner = LLMCompletionError("connection reset again", error_category=InferenceErrorCategory.TRANSIENT)
        outer.__cause__ = inner
        inner.__cause__ = outer
        wrapper = _WrapperError("Pipe 'greet' failed")
        wrapper.__cause__ = outer

        assert outer.resolve_error_code() == CoreCode.PROVIDER_UNAVAILABLE
        assert outer.to_error_report().code == CoreCode.PROVIDER_UNAVAILABLE
        assert wrapper.to_error_report().code == CoreCode.PROVIDER_UNAVAILABLE
        assert find_root_fault(error=wrapper) is inner
