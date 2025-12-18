from pipelex.base_exceptions import PipelexError


class StuffSpecError(PipelexError):
    def __init__(self, message: str, pipe_code: str, missing_inputs: dict[str, str]):
        self.pipe_code = pipe_code
        self.missing_inputs = missing_inputs
        super().__init__(message)


class PipePortError(PipelexError):
    def __init__(self, message: str, pipe_code: str, concept_code: str | None = None):
        self.pipe_code = pipe_code
        self.concept_code = concept_code
        super().__init__(message)


class PipePortInputError(PipePortError):
    def __init__(self, message: str, pipe_code: str, variable_name: str, concept_code: str):
        self.variable_name = variable_name
        super().__init__(message, pipe_code, concept_code)


class PipePortOutputError(PipePortError):
    def __init__(self, message: str, pipe_code: str, concept_code: str):
        super().__init__(message, pipe_code, concept_code)


class PipePortInputNotFoundError(PipelexError):
    pass


class PipeInputsFactoryError(PipelexError):
    pass
