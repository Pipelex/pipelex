from pipelex.base_exceptions import PipelexError


class PipeSequenceBlueprintValueError(ValueError):
    pass


class PipeSequenceValueError(ValueError):
    pass


class PipeSequenceFactoryError(PipelexError):
    pass
