from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData


class PipelexInterpreterError(PipelexError):
    """Raised when PipelexInterpreter fails.

    Covers every way the caller's ``.mthds`` source can be rejected — TOML that
    does not parse, and TOML that parses but fails blueprint validation. The
    message is always caller-facing copy describing a fault in the caller's own
    input.
    """

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
