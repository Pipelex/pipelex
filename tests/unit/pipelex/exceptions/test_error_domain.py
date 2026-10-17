from enum import StrEnum

import pytest
from mthds.protocol.problem.registry import ProblemDomain

from pipelex.base_exceptions import ErrorDomain, PipelexError, error_domain_is_input
from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class _ConfigCodedError(PipelexError):
    """Test-only subclass whose code is in the operator's domain."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class TestErrorDomain:
    """Tests for the ErrorDomain enum and error_domain on the error model."""

    def test_error_domain_is_str_enum(self) -> None:
        """ErrorDomain is a StrEnum."""
        assert issubclass(ErrorDomain, StrEnum)

    def test_error_domain_values(self) -> None:
        """ErrorDomain has INPUT, CONFIG, RUNTIME with the expected string values."""
        assert ErrorDomain.INPUT == "input"
        assert ErrorDomain.CONFIG == "config"
        assert ErrorDomain.RUNTIME == "runtime"
        assert set(ErrorDomain) == {ErrorDomain.INPUT, ErrorDomain.CONFIG, ErrorDomain.RUNTIME}

    def test_an_error_with_no_code_is_in_the_runtime_domain(self) -> None:
        """A PipelexError that names no code reports runtime.unexpected, and so the runtime domain."""
        problem = PipelexError("plain error").to_problem(view=ProblemView.CALLER)
        assert problem.code == "runtime.unexpected"
        assert ErrorDomain.from_problem_domain(problem.effective_domain) is ErrorDomain.RUNTIME

    def test_the_domain_is_read_from_the_code(self) -> None:
        """A PipelexError subclass reads its domain from its code's registry domain."""
        error = _ConfigCodedError("config broke")
        assert error.resolve_domain() == ProblemDomain.OPERATOR
        assert ErrorDomain.from_problem_domain(error.resolve_domain()) is ErrorDomain.CONFIG

    @pytest.mark.parametrize(
        ("problem_domain", "expected_error_domain"),
        [
            (ProblemDomain.INPUT, ErrorDomain.INPUT),
            (ProblemDomain.METHOD, ErrorDomain.INPUT),
            (ProblemDomain.ACCOUNT, ErrorDomain.CONFIG),
            (ProblemDomain.OPERATOR, ErrorDomain.CONFIG),
            (ProblemDomain.RUNTIME, ErrorDomain.RUNTIME),
        ],
    )
    def test_from_problem_domain(self, problem_domain: ProblemDomain, expected_error_domain: ErrorDomain) -> None:
        """A code's registry domain projects onto the envelope's domain: the caller's, the operator's or the runtime's."""
        assert ErrorDomain.from_problem_domain(problem_domain) is expected_error_domain

    @pytest.mark.parametrize(
        ("error_domain", "expected_is_input"),
        [
            (ErrorDomain.INPUT, True),
            (ErrorDomain.CONFIG, False),
            (ErrorDomain.RUNTIME, False),
        ],
    )
    def test_is_input(self, error_domain: ErrorDomain, expected_is_input: bool) -> None:
        """ErrorDomain.is_input is True only for INPUT — caller-fixable input faults."""
        assert error_domain.is_input is expected_is_input

    @pytest.mark.parametrize(
        ("error_domain", "expected_is_input"),
        [
            (ErrorDomain.INPUT, True),
            ("input", True),
            (ErrorDomain.CONFIG, False),
            ("config", False),
            (ErrorDomain.RUNTIME, False),
            ("runtime", False),
            (None, False),
            ("not_a_domain", False),
        ],
    )
    def test_error_domain_is_input(self, error_domain: ErrorDomain | str | None, expected_is_input: bool) -> None:
        """error_domain_is_input tolerates the serialized str/None shape a CLI envelope's error_domain carries."""
        assert error_domain_is_input(error_domain) is expected_is_input
