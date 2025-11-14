from pipelex.base_exceptions import PipelexError


class PipeConditionBlueprintValueError(ValueError):
    pass


class PipeConditionValueError(ValueError):
    pass


class PipeConditionFactoryError(PipelexError):
    pass


class PipeConditionRunError(PipelexError):
    pass
