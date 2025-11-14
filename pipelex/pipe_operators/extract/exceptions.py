from pipelex.base_exceptions import PipelexError


class PipeExtractBlueprintValueError(ValueError):
    pass


class PipeExtractValueError(ValueError):
    pass


class PipeExtractFactoryError(PipelexError):
    pass
