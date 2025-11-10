from pipelex.base_exceptions import PipelexException
from pipelex.pipe_run.pipe_run_mode import PipeRunMode


class PipeRunParamsError(PipelexException):
    pass


class BatchParamsError(PipelexException):
    pass


class PipeRunError(PipelexException):
    pass


class PipeRouterError(PipelexException):
    def __init__(
        self,
        message: str,
        run_mode: PipeRunMode,
        pipe_code: str,
        output_name: str | None,
        pipe_stack: list[str],
        missing_inputs: list[str] | None = None,
    ):
        self.run_mode = run_mode
        self.pipe_code = pipe_code
        self.output_name = output_name
        self.pipe_stack = pipe_stack
        self.missing_inputs = missing_inputs
        super().__init__(message)
