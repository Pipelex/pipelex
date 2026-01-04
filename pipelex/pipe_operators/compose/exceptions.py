from pipelex.base_exceptions import PipelexError


class PipeComposeError(PipelexError):
    pass


class PipeComposeFactoryError(PipeComposeError):
    pass


class ConstructFieldBlueprintTypeError(PipeComposeError, TypeError):
    pass


class ConstructFieldBlueprintValueError(PipeComposeError, ValueError):
    pass


class StructuredContentComposerTypeError(PipeComposeError, TypeError):
    pass


class StructuredContentComposerValueError(PipeComposeError, ValueError):
    pass


class StructuredContentComposerValidationError(PipeComposeError):
    pass
