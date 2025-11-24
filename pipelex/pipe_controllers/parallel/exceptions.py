from pipelex.base_exceptions import PipelexError
from pipelex.core.pipes.exceptions import PipeDryRunError, PipeRunError


class PipeParallelValueError(ValueError):
    pass


class PipeParallelFactoryError(PipelexError):
    pass


class PipeParallelRunError(PipeRunError):
    pass


class PipeParallelDryRunError(PipeDryRunError):
    pass
