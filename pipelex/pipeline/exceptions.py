from pipelex.exceptions import PipelexException
from pipelex.pipe_run.pipe_run_mode import PipeRunMode


class PipeExecutionError(PipelexException):
    pass

class PipelineExecutionError(PipelexException):
    def __init__(
        self,
        message: str,
        run_mode: PipeRunMode,
        pipe_code: str,
        output_name: str | None,
        pipe_stack: list[str],
    ):
        self.run_mode = run_mode
        self.pipe_code = pipe_code
        self.output_name = output_name
        self.pipe_stack = pipe_stack
        super().__init__(message)


