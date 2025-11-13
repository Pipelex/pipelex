from pipelex.base_exceptions import PipelexException


class PipeExtractBlueprintValueError(ValueError):
    pass


class PipeExtractValueError(ValueError):
    pass


class PipeExtractFactoryError(PipelexException):
    pass
