from pipelex.base_exceptions import PipelexError


class ModelReferenceParseError(PipelexError):
    """Error raised when a model reference string cannot be parsed.

    Includes helpful syntax guide in error message.
    """

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
