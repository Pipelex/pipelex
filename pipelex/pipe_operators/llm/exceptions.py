from pipelex.base_exceptions import PipelexError


class LLMPromptBlueprintValueError(ValueError):
    pass


class PipeLLMValueError(ValueError):
    pass


class PipeLLMFactoryError(PipelexError):
    pass
