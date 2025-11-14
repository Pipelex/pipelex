from pipelex.base_exceptions import PipelexError


class PipeImgGenBlueprintValueError(ValueError):
    pass


class PipeImgGenValueError(ValueError):
    pass


class PipeImgGenFactoryError(PipelexError):
    pass


class PipeImgGenRunError(PipelexError):
    pass
