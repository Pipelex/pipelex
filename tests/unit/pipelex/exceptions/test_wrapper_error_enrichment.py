from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory
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
    """PipelineExecutionError must surface the wrapped cause's categorized action, not mask it with its generic floor."""

    def test_preserves_categorized_cause_action(self) -> None:
        """A transient CogtError wrapped through PipeRunError/PipeRouterError keeps its WAIT_AND_RETRY action and category."""
        cogt_error = CogtError(
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
        assert report.retryable is True

    def test_surfaces_input_domain_of_a_content_categorized_cause(self) -> None:
        """A CONTENT-categorized CogtError reaches the wrapper as INPUT / 422, not the generic RUNTIME floor.

        This is what the class docstring has always promised — that the RUNTIME floor applies only
        when the cause chain surfaces no domain. Until the CogtError family derived a domain from its
        category, no inference failure ever surfaced one, so the promise was vacuous and the floor
        fired every time.
        """
        cogt_error = CogtError(message="the prompt was refused", error_category=InferenceErrorCategory.CONTENT)
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

        assert report.error_domain == ErrorDomain.INPUT, "the wrapper's RUNTIME floor must not mask a caller-fixable cause"
        assert report.http_status == 422
        assert report.error_category == InferenceErrorCategory.CONTENT

    def test_falls_back_to_runtime_unknown_without_cause(self) -> None:
        """With no PipelexError cause, PipelineExecutionError reports the generic RUNTIME / UNKNOWN floor."""
        report = _make_pipeline_execution_error(cause=None).to_error_report()

        assert report.error_domain == ErrorDomain.RUNTIME
        assert report.user_action is not None
        assert report.user_action.kind == UserActionKind.UNKNOWN
        assert report.user_action.detail == "Check pipe_stack to identify which pipe failed"
