from pipelex.base_exceptions import PipelexError


class StuffSpecError(PipelexError):
    def __init__(self, message: str, pipe_code: str, missing_inputs: dict[str, str]):
        self.pipe_code = pipe_code
        self.missing_inputs = missing_inputs
        super().__init__(message)


class PipeInputsFactoryError(PipelexError):
    pass
