from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.types import StrEnum
from tests.helpers.error_report import make_error_report


class _ConfigDomainError(PipelexError):
    """Test-only subclass that declares a class-level error_domain."""

    error_domain = ErrorDomain.CONFIG


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

    def test_to_error_report_omits_error_domain_when_undeclared(self) -> None:
        """A PipelexError that declares no error_domain reports it as None."""
        report = PipelexError("plain error").to_error_report()
        assert report.error_domain is None

    def test_to_error_report_carries_error_domain_when_declared(self) -> None:
        """A PipelexError subclass with a class-level error_domain forwards it into the report."""
        report = _ConfigDomainError("config broke").to_error_report()
        assert report.error_domain == ErrorDomain.CONFIG
        assert report.error_domain == "config"

    def test_to_dict_drops_error_domain_when_none(self) -> None:
        """ErrorReport.to_dict() omits error_domain when it is None."""
        report_dict = make_error_report(error_type="X", message="m").to_dict()
        assert "error_domain" not in report_dict

    def test_to_dict_includes_error_domain_when_set(self) -> None:
        """ErrorReport.to_dict() includes error_domain when it is set."""
        report_dict = make_error_report(error_type="X", message="m", error_domain=ErrorDomain.CONFIG).to_dict()
        assert report_dict["error_domain"] == "config"
