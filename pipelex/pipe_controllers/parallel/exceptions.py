from pipelex.base_exceptions import PipelexError


class PipeParallelBlueprintValueError(ValueError):
    pass


class PipeParallelValueError(ValueError):
    pass


class PipeParallelFactoryError(PipelexError):
    pass
