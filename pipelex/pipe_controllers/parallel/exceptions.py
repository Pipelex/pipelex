from pipelex.base_exceptions import PipelexException


class PipeParallelBlueprintValueError(ValueError):
    pass


class PipeParallelValueError(ValueError):
    pass


class PipeParallelFactoryError(PipelexException):
    pass
