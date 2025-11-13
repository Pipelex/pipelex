from pipelex.base_exceptions import PipelexException


class PipeBatchValueError(ValueError):
    pass


class PipeBatchFactoryError(PipelexException):
    pass


class PipeBatchRunError(PipelexException):
    pass
