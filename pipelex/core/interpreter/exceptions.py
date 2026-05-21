from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.tools.misc.toml_utils import TomlError


class PipelexInterpreterError(PipelexError):
    """Raised when PipelexInterpreter fails."""

    error_domain = ErrorDomain.INPUT
    # The interpreter's messages describe faults in the caller's own .mthds
    # source — caller-facing copy, kept verbatim under STRICT disclosure.
    _authors_caller_facing_message = True

    def __init__(
        self,
        message: str,
        validation_errors: list[PipelexBundleBlueprintValidationErrorData] | None = None,
    ):
        self.validation_errors = validation_errors or []
        super().__init__(message)


class MthdsDecodeError(TomlError):
    """Raised when MTHDS decoding fails."""
