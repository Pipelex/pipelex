from typing import Any, cast

from pydantic import TypeAdapter
from pydantic.dataclasses import dataclass

from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction
from pipelex.types import StrEnum


class ErrorDomain(StrEnum):
    """Classifies where an error originates, so consumers can route it.

    - INPUT: the caller can fix it (bad .mthds, wrong args, malformed JSON).
    - CONFIG: an environment or configuration change is needed.
    - RUNTIME: a failure that occurred during execution.
    """

    INPUT = "input"
    CONFIG = "config"
    RUNTIME = "runtime"


def error_domain_to_http_status(error_domain: ErrorDomain | None) -> int:
    """Map an :class:`ErrorDomain` to an HTTP status code.

    Authoritative mapping for downstream HTTP APIs (``pipelex-relay``,
    ``pipelex-back-office``): those repos call this helper instead of
    redefining the contract. The library itself stays HTTP-agnostic — no
    web-framework import lives here, only the mapping table.

    - ``INPUT`` -> 422: the caller sent something it can fix (bad input).
    - ``CONFIG`` / ``RUNTIME`` -> 500: a server-side problem.
    - ``None`` -> 500: unclassified, treated as a server-side problem.

    This is the *domain* default. A provider 429 (rate-limit) passthrough is
    layered on top by :attr:`ErrorReport.http_status`.
    """
    match error_domain:
        case ErrorDomain.INPUT:
            return 422
        case ErrorDomain.CONFIG | ErrorDomain.RUNTIME:
            return 500
        case None:
            return 500


@dataclass(frozen=True, config={"extra": "forbid", "arbitrary_types_allowed": True})
class ErrorReport:
    """Structured error report — single source of truth for all error serialization.

    Used by CLI JSON output, agent output, and Temporal error details.
    """

    error_type: str
    message: str
    error_category: str | None = None
    error_domain: str | None = None
    retryable: bool | None = None
    user_action: UserAction | None = None
    model: str | None = None
    provider: str | None = None
    provider_metadata: ProviderErrorMetadata | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a dict with only non-None fields."""
        return cast(
            "dict[str, Any]",
            TypeAdapter(type(self)).dump_python(self, mode="python", exclude_none=True),
        )

    def user_action_detail(self) -> str | None:
        """Return the free-form advice text on ``user_action``, or ``None`` when absent."""
        return self.user_action.detail if self.user_action is not None else None

    @property
    def http_status(self) -> int:
        """HTTP status code for this error, for downstream HTTP API adapters.

        A provider 429 (rate limit) takes precedence so the API can surface a
        ``Retry-After`` header from ``provider_metadata.retry_after_seconds``;
        otherwise the status follows ``error_domain`` (see
        :func:`error_domain_to_http_status`).
        """
        if self.provider_metadata is not None and self.provider_metadata.status_code == 429:
            return 429
        domain = ErrorDomain(self.error_domain) if self.error_domain is not None else None
        return error_domain_to_http_status(domain)


class PipelexError(Exception):
    error_domain: ErrorDomain | None = None
    user_action: UserAction | None = None

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def to_error_report(self) -> ErrorReport:
        """Return a structured error report.

        Subclasses override to include additional fields (error_category, model, etc.).
        """
        return ErrorReport(
            error_type=type(self).__name__,
            message=self.message,
            error_domain=self.error_domain,
            user_action=self.user_action,
        )


class PipelexUnexpectedError(PipelexError):
    pass


class PipelexConfigError(PipelexError):
    error_domain = ErrorDomain.CONFIG


class PipelexSetupError(PipelexError):
    error_domain = ErrorDomain.CONFIG


class SecurityError(PipelexError):
    """Base for security-policy violations.

    Kept distinct from domain errors so security signals are not silently
    swallowed by domain-level `except` handlers (e.g. `except PipelexError`).
    """
