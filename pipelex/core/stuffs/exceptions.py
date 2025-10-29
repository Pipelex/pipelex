from pipelex.exceptions import PipelexException

class StuffArtefactError(PipelexException):
    pass

class StuffArtefactReservedFieldError(StuffArtefactError):
    pass
