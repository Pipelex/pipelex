from pipelex.exceptions import PipelexException

class PipeBlueprintValueError(ValueError):
    pass

class PipeInputNotFoundError(PipelexException):
    pass
class PipeFactoryError(PipelexException):
    pass

class PipeLibraryPipeNotFoundError(PipeLibraryError):
    pass