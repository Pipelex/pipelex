from pipelex.base_exceptions import PipelexException


class PipeComposeBlueprintValueError(ValueError):
    pass


class PipeComposeValueError(ValueError):
    pass


class PipeComposeFactoryError(PipelexException):
    pass
