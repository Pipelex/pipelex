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


def error_domain_to_http_status(error_domain: ErrorDomain | str | None) -> int:
    """Map an error domain to an HTTP status code.

    Domain-level building block for downstream HTTP APIs (``pipelex-relay``,
    ``pipelex-back-office``). When you have a full :class:`ErrorReport`, prefer
    :attr:`ErrorReport.http_status` — it layers the provider 429 (rate-limit)
    passthrough on top of this mapping. The library itself stays HTTP-agnostic —
    no web-framework import lives here, only the mapping table.

    Accepts a raw ``str`` because ``ErrorReport.error_domain`` is serialized as
    one. A value this version does not recognize (e.g. a report serialized by a
    newer Pipelex) is treated as unclassified rather than crashing rendering.

    - ``INPUT`` -> 422: the caller sent something it can fix (bad input).
    - ``CONFIG`` / ``RUNTIME`` -> 500: a server-side problem.
    - unknown / ``None`` -> 500: unclassified, treated as a server-side problem.
    """
    if isinstance(error_domain, str):
        try:
            error_domain = ErrorDomain(error_domain)
        except ValueError:
            error_domain = None
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
        :func:`error_domain_to_http_status`, which also tolerates an
        ``error_domain`` string this version does not recognize — e.g. a report
        serialized by a newer Pipelex — rather than crashing response rendering).
        """
        if self.provider_metadata is not None and self.provider_metadata.status_code == 429:
            return 429
        return error_domain_to_http_status(self.error_domain)


class PipelexError(Exception):
    error_domain: ErrorDomain | None = None
    user_action: UserAction | None = None

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def to_error_report(self) -> ErrorReport:
        """Return a structured error report, enriched from the ``__cause__`` chain.

        Wrapper exceptions (``PipeRunError`` -> ``PipeRouterError`` ->
        ``PipelineExecutionError``) carry no ``error_category`` / ``retryable`` /
        ``model`` / ``provider`` of their own. This surfaces those classification
        fields from the underlying exception (typically a ``CogtError``) so they
        survive every wrapping layer up to the CLI / HTTP boundary.

        Subclasses override to include additional fields (error_category, model,
        etc.); an override must end with ``self._enrich_error_report_from_cause(report)``
        so the cause-chain enrichment stays uniform across the hierarchy.
        """
        report = ErrorReport(
            error_type=type(self).__name__,
            message=self.message,
            error_domain=self.error_domain,
            user_action=self.user_action,
        )
        return self._enrich_error_report_from_cause(report)

    def _enrich_error_report_from_cause(self, report: ErrorReport) -> ErrorReport:
        """Fill the ``None`` classification fields of ``report`` from the ``__cause__`` chain.

        A wrapper keeps its own ``error_type`` and ``message`` but inherits every
        classification field it does not set itself — ``error_category``,
        ``error_domain``, ``retryable``, ``user_action``, ``model``, ``provider``,
        ``provider_metadata`` — from the underlying ``PipelexError`` that knows them.
        ``to_error_report()`` overrides call this so enrichment stays uniform.
        """
        cause = self.__cause__
        if not isinstance(cause, PipelexError):
            return report
        cause_report = cause.to_error_report()
        return ErrorReport(
            error_type=report.error_type,
            message=report.message,
            error_category=report.error_category or cause_report.error_category,
            error_domain=report.error_domain or cause_report.error_domain,
            retryable=report.retryable if report.retryable is not None else cause_report.retryable,
            user_action=report.user_action or cause_report.user_action,
            model=report.model or cause_report.model,
            provider=report.provider or cause_report.provider,
            provider_metadata=report.provider_metadata or cause_report.provider_metadata,
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
