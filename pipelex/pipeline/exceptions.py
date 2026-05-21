from typing_extensions import override

from pipelex.base_exceptions import ErrorDomain, ErrorReport, PipelexError, PipelexUnexpectedError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.pipe_run.pipe_run_mode import PipeRunMode


class PipeExecutionError(PipelexError):
    error_domain = ErrorDomain.RUNTIME


class PipelineExecutionError(PipelexError):
    """Wraps any failure that occurred while running a pipeline.

    Being a pure wrapper, it has no authoritative classification of its own:
    ``to_error_report()`` inherits ``error_domain`` / ``user_action`` from the
    wrapped ``__cause__`` chain (so a categorized ``CogtError`` keeps its
    ``WAIT_AND_RETRY`` / ``CHECK_BILLING`` action), and only falls back to a
    generic RUNTIME / UNKNOWN classification when the cause chain surfaces none.
    """

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
        self.pipe_stack = list(pipe_stack)  # snapshot: the live stack unwinds after this error is raised
        super().__init__(message)

    @override
    def to_error_report(self) -> ErrorReport:
        # The report is first enriched from the __cause__ chain; the generic
        # RUNTIME / UNKNOWN values are only a floor, applied when the cause
        # surfaced nothing — never overriding a categorized cause action.
        report = super().to_error_report()
        return report.model_copy(
            update={
                "error_domain": report.error_domain or ErrorDomain.RUNTIME,
                "user_action": report.user_action or UserAction(kind=UserActionKind.UNKNOWN, detail="Check pipe_stack to identify which pipe failed"),
            }
        )


class PipeStackOverflowError(PipelexError):
    def __init__(self, message: str, limit: int, pipe_stack: list[str]):
        self.limit = limit
        self.pipe_stack = list(pipe_stack)  # snapshot: the live stack unwinds after this error is raised
        super().__init__(message)


class JobMetadataError(PipelexUnexpectedError):
    pass
