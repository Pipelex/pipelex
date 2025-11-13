from pipelex.base_exceptions import PipelexException


class PipeSequenceBlueprintValueError(ValueError):
    pass


class PipeSequenceValueError(ValueError):
    pass


class PipeSequenceFactoryError(PipelexException):
    pass
