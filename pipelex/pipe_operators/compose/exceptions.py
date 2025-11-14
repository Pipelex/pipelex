from pipelex.base_exceptions import PipelexError


class PipeComposeBlueprintValueError(ValueError):
    pass


class PipeComposeValueError(ValueError):
    pass


class PipeComposeFactoryError(PipelexError):
    pass
