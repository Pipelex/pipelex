from pipelex.base_exceptions import PipelexException
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.pipe_run.exceptions import PipeRunError
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


class DryRunError(PipeRunError):
    """Raised when a dry run fails due to missing inputs or other validation issues."""

    def __init__(self, message: str, pipe_type: str, pipe_code: str | None = None):
        self.pipe_type = pipe_type
        self.pipe_code = pipe_code
        super().__init__(message)


class DryRunMissingInputsError(DryRunError):
    """Raised when a dry run fails due to missing inputs or other validation issues."""

    def __init__(self, message: str, pipe_type: str, pipe_code: str, missing_inputs: list[str] | None = None):
        self.missing_inputs = missing_inputs or []
        super().__init__(message, pipe_type, pipe_code)


class DryRunMissingPipesError(DryRunError):
    """Raised when a dry run fails due to missing pipes or other validation issues."""

    def __init__(self, message: str, pipe_type: str, pipe_code: str, missing_pipes: list[str] | None = None):
        self.missing_pipes = missing_pipes or []
        super().__init__(message, pipe_type, pipe_code)


class DryRunTemplatingError(DryRunError):
    """Raised when a dry run fails due to templating issues."""

    def __init__(self, message: str, pipe_type: str, pipe_code: str, template_category: TemplateCategory, template: str):
        self.template_category = template_category
        self.template = template
        super().__init__(message, pipe_type, pipe_code)


class PipeStackOverflowError(PipelexException):
    def __init__(self, message: str, limit: int, pipe_stack: list[str]):
        self.limit = limit
        self.pipe_stack = pipe_stack
        super().__init__(message)
