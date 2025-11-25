from pipelex.base_exceptions import PipelexError
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.tools.misc.toml_utils import TomlError


class PipelexInterpreterError(PipelexError):
    """Raised when PipelexInterpreter fails."""

    def __init__(
        self,
        message: str,
        validation_errors: list[PipelexBundleBlueprintValidationErrorData] | None = None,
    ):
        self.validation_errors = validation_errors or []
        super().__init__(message)


class PLXDecodeError(TomlError):
    """Raised when PLX decoding fails."""
