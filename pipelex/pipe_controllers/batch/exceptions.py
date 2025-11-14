from pipelex.base_exceptions import PipelexError


class PipeBatchValueError(ValueError):
    pass


class PipeBatchFactoryError(PipelexError):
    pass


class PipeBatchRunError(PipelexError):
    pass
