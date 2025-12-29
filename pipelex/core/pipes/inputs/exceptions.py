from pipelex.base_exceptions import PipelexError
from pipelex.pipe_run.exceptions import PipeRunError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode


class InputStuffSpecsError(PipelexError):
    pass


class InputStuffSpecsFactoryError(InputStuffSpecsError):
    pass


class InputStuffSpecNotFoundError(InputStuffSpecsError):
    pass


class PipeInputError(PipelexError):
    def __init__(
        self,
        message: str,
        pipe_code: str,
        variable_name: str | None = None,
        concept_code: str | None = None,
    ):
        self.pipe_code = pipe_code
        self.variable_name = variable_name
        self.concept_code = concept_code
        super().__init__(message)


class PipeRunInputsError(PipeRunError):
    def __init__(
        self,
        message: str,
        run_mode: PipeRunMode,
        pipe_code: str,
        missing_inputs: list[str] | None = None,
        variable_name: str | None = None,
        concept_code: str | None = None,
    ):
        self.missing_inputs = missing_inputs
        self.variable_name = variable_name
        self.concept_code = concept_code
        super().__init__(message, run_mode, pipe_code)
