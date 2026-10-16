from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ErrorCodeSet
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class ModelReferenceParseError(PipelexError):
    """Error raised when a model reference string cannot be parsed.

    Includes helpful syntax guide in error message. ``method.model_setting_invalid`` for a reference a method
    writes, and ``pipelex.config.invalid`` for one the model deck writes, which a site that knows the reference is
    the deck's chooses; the parser itself cannot tell.
    """

    error_code = ErrorCodeSet(default=CoreCode.METHOD_MODEL_SETTING_INVALID, others=(PipelexErrorCode.CONFIG_INVALID,))

    def __init__(self, message: str, raw_value: str):
        self.raw_value = raw_value
        syntax_help = (
            "\n\nModel reference syntax:\n"
            "  - Preset:    $preset_name or preset:preset_name\n"
            "  - Alias:     @alias_name or alias:alias_name\n"
            "  - Waterfall: ~waterfall_name or waterfall:waterfall_name\n"
            "  - Handle:    model_handle or handle:model_handle"
        )
        full_message = f"{message}{syntax_help}"
        super().__init__(message=full_message)
