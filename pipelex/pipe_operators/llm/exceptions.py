from pipelex.base_exceptions import PipelexException


class LLMPromptBlueprintValueError(ValueError):
    pass


class PipeLLMValueError(ValueError):
    pass


class PipeLLMFactoryError(PipelexException):
    pass
