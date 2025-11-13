from pipelex.base_exceptions import PipelexException


class PipeImgGenBlueprintValueError(ValueError):
    pass


class PipeImgGenValueError(ValueError):
    pass


class PipeImgGenFactoryError(PipelexException):
    pass


class PipeImgGenRunError(PipelexException):
    pass
