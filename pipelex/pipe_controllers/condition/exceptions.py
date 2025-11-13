from pipelex.base_exceptions import PipelexException


class PipeConditionError(PipelexException):
    pass


class PipeConditionBlueprintValueError(ValueError):
    pass
