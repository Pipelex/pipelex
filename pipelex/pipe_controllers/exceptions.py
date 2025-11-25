from pipelex.base_exceptions import PipelexError


class PipeControllerError(PipelexError):
    pass


class PipeControllerOutputConceptMismatchError(PipeControllerError):
    def __init__(self, message: str, tested_concept: str, wanted_concept: str):
        self.tested_concept = tested_concept
        self.wanted_concept = wanted_concept
        super().__init__(message)
