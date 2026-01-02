from pipelex.base_exceptions import PipelexError


class PipeComposeError(PipelexError):
    pass


class PipeComposeFactoryError(PipeComposeError):
    pass


class ConstructFieldBlueprintTypeError(PipeComposeError, TypeError):
    pass


class ConstructFieldBlueprintValueError(PipeComposeError, ValueError):
    pass
