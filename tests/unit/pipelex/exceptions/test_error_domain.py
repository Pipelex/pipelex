from enum import StrEnum

import pytest
from mthds.protocol.problem.registry import ProblemDomain

from pipelex.base_exceptions import ErrorDomain, PipelexError, error_domain_is_input
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from tests.helpers.error_report import make_error_report


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

    def test_to_error_report_reports_the_fallback_domain_without_a_code(self) -> None:
        """A PipelexError that names no code reports runtime.unexpected, and so the runtime domain."""
        report = PipelexError("plain error").to_error_report()
        assert report.code == "runtime.unexpected"
        assert report.error_domain == ErrorDomain.RUNTIME

    def test_to_error_report_reads_the_domain_from_the_code(self) -> None:
        """A PipelexError subclass's report reads its domain from its code's registry domain."""
        report = _ConfigCodedError("config broke").to_error_report()
        assert report.error_domain == ErrorDomain.CONFIG
        assert report.error_domain == "config"

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
        """A code's registry domain projects onto the report's domain: the caller's, the operator's or the runtime's."""
        assert ErrorDomain.from_problem_domain(problem_domain) is expected_error_domain

    def test_to_dict_drops_error_domain_when_none(self) -> None:
        """ErrorReport.to_dict() omits error_domain when it is None."""
        report_dict = make_error_report(error_type="X", message="m").to_dict()
        assert "error_domain" not in report_dict

    def test_to_dict_includes_error_domain_when_set(self) -> None:
        """ErrorReport.to_dict() includes error_domain when it is set."""
        report_dict = make_error_report(error_type="X", message="m", error_domain=ErrorDomain.CONFIG).to_dict()
        assert report_dict["error_domain"] == "config"

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
        """error_domain_is_input tolerates the serialized str/None shape ErrorReport.error_domain carries."""
        assert error_domain_is_input(error_domain) is expected_is_input
