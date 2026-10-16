from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import InheritsCause
from pipelex.system.pipe_run_mode import PipeRunMode


class PipeOperatorModelAvailabilityError(PipelexError):
    """An operator found no model to run: the model it names is unknown, or no backend serves it.

    It takes its cause's code, the model lookup's own (``model.unknown`` for the method's reference,
    ``model.unavailable`` for this deployment's backends), and falls back to the deployment serving no backend.
    """

    error_code = InheritsCause(fallback=CoreCode.MODEL_UNAVAILABLE)

    def __init__(
        self,
        message: str,
        run_mode: PipeRunMode,
        pipe_type: str,
        pipe_code: str,
        pipe_stack: list[str],
        model_handle: str | None,
        fallback_list: list[str] | None = None,
    ):
        self.run_mode = run_mode
        self.pipe_type = pipe_type
        self.pipe_code = pipe_code
        self.pipe_stack = list(pipe_stack)  # snapshot: the live stack unwinds after this error is raised
        self.model_handle = model_handle
        self.fallback_list = fallback_list
        super().__init__(message)
