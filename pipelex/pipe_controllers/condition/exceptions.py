from pipelex.base_exceptions import PipelexException


class PipeConditionBlueprintValueError(ValueError):
    pass


class PipeConditionValueError(ValueError):
    pass


class PipeConditionFactoryError(PipelexException):
    pass


class PipeConditionRunError(PipelexException):
    pass
