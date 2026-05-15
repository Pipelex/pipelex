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
