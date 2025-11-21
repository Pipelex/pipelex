from pipelex.base_exceptions import PipelexError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode


class PipeOperatorModelAvailabilityError(PipelexError):
    def __init__(
        self,
        message: str,
        run_mode: PipeRunMode,
        pipe_type: str,
        pipe_code: str,
        pipe_stack: list[str],
        model_handle: str,
        fallback_list: list[str] | None = None,
    ):
        self.run_mode = run_mode
        self.pipe_type = pipe_type
        self.pipe_code = pipe_code
        self.pipe_stack = pipe_stack
        self.model_handle = model_handle
        self.fallback_list = fallback_list
        super().__init__(message)
