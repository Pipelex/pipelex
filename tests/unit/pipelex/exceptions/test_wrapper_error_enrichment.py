from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.system.pipe_run_mode import PipeRunMode


def _make_pipeline_execution_error(cause: BaseException | None) -> PipelineExecutionError:
    error = PipelineExecutionError(
        message="pipeline failed",
        run_mode=PipeRunMode.LIVE,
        pipe_code="some_pipe",
        output_name=None,
        pipe_stack=["some_pipe"],
    )
    if cause is not None:
        error.__cause__ = cause
    return error


class TestWrapperErrorEnrichment:
    """PipelineExecutionError must surface the wrapped cause's code and categorized action, not mask them."""

    def test_preserves_categorized_cause_action(self) -> None:
        """A transient inference failure wrapped through PipeRunError/PipeRouterError keeps its action, its category and its retryable code."""
        cogt_error = LLMCompletionError(
            message="rate limited",
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(kind=UserActionKind.WAIT_AND_RETRY, detail="Wait a moment and retry"),
        )
        pipe_run_error = PipeRunError(message="pipe failed", run_mode=PipeRunMode.LIVE, pipe_code="some_pipe")
        pipe_run_error.__cause__ = cogt_error
        pipe_router_error = PipeRouterError(
            message="router failed",
            run_mode=PipeRunMode.LIVE,
            pipe_code="some_pipe",
            output_name=None,
            pipe_stack=["some_pipe"],
        )
        pipe_router_error.__cause__ = pipe_run_error

        report = _make_pipeline_execution_error(cause=pipe_router_error).to_error_report()

        assert report.user_action is not None
        assert report.user_action.kind == UserActionKind.WAIT_AND_RETRY, "the cause's actionable advice must not be masked by the wrapper"
        assert report.user_action.detail == "Wait a moment and retry"
        assert report.error_category == InferenceErrorCategory.TRANSIENT
        # A category with no code of its own reports the category's code, which invites a retry.
        assert report.code == CoreCode.PROVIDER_UNAVAILABLE
        assert report.retryable is True

    def test_surfaces_the_code_of_a_caller_fixable_cause(self) -> None:
        """A content refusal coded `model.content_refused` reaches the wrapper as its code, INPUT / 422, not a runtime fault.

        The run's wrappers take their cause's code, so the report reads the refusal's own code and every fact it
        decides, rather than the runtime fault a wrapper with a code of its own would report.
        """
        cogt_error = LLMCompletionError(message="the prompt was refused", error_category=InferenceErrorCategory.CONTENT).with_error_code(
            CoreCode.MODEL_CONTENT_REFUSED
        )
        pipe_run_error = PipeRunError(message="pipe failed", run_mode=PipeRunMode.LIVE, pipe_code="some_pipe")
        pipe_run_error.__cause__ = cogt_error
        pipe_router_error = PipeRouterError(
            message="router failed",
            run_mode=PipeRunMode.LIVE,
            pipe_code="some_pipe",
            output_name=None,
            pipe_stack=["some_pipe"],
        )
        pipe_router_error.__cause__ = pipe_run_error

        report = _make_pipeline_execution_error(cause=pipe_router_error).to_error_report()

        assert report.code == CoreCode.MODEL_CONTENT_REFUSED
        assert report.error_domain == ErrorDomain.INPUT, "the wrapper must not mask a caller-fixable cause"
        assert report.http_status == 422
        assert report.error_category == InferenceErrorCategory.CONTENT

    def test_falls_back_to_runtime_unknown_without_cause(self) -> None:
        """With no PipelexError cause, PipelineExecutionError reports its fallback code and a next step naming the failing pipe."""
        report = _make_pipeline_execution_error(cause=None).to_error_report()

        assert report.code == CoreCode.RUNTIME_UNEXPECTED
        assert report.error_domain == ErrorDomain.RUNTIME
        assert report.user_action is not None
        assert report.user_action.kind == UserActionKind.UNKNOWN
        assert report.user_action.detail == "The run failed in pipe 'some_pipe': the message gives the cause."
