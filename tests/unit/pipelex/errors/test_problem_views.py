import logging
from typing import Any, ClassVar, cast

import pytest
from mthds.protocol.problem.registry import CoreCode, StepKind
from pydantic import BaseModel

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.errors.error_code_declaration import ErrorCodeDeclaration
from pipelex.errors.error_codes import ErrorCode, error_code_spec
from pipelex.errors.problem import (
    MAX_PROBLEM_TEXT_LENGTH,
    TRUNCATION_MARKER,
    PipelexProblem,
    ProblemView,
    caller_view_of,
    make_problem,
    problem_metadata,
)
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from tests.unit.pipelex.errors.test_data import ProblemViewsTestData


class _MisconfiguredError(PipelexError):
    error_code: ClassVar[ErrorCodeDeclaration] = CoreCode.RUNTIME_MISCONFIGURED


class _TemplateRefusalError(PipelexError):
    error_code: ClassVar[ErrorCodeDeclaration] = CoreCode.METHOD_TEMPLATE_INVALID


class _NodeHolder(BaseModel):
    error: PipelexProblem | None = None


def _all_codes() -> list[ErrorCode]:
    return [*CoreCode, *PipelexErrorCode]


def _nulls_in(value: Any, *, path: str = "") -> list[str]:
    """The paths of every member of ``value``, at any depth, written as ``None``."""
    if value is None:
        return [path or "<root>"]
    if isinstance(value, dict):
        found: list[str] = []
        for key, item in cast("dict[str, Any]", value).items():
            found.extend(_nulls_in(item, path=f"{path}.{key}"))
        return found
    if isinstance(value, list):
        found = []
        for index_item, item in enumerate(cast("list[Any]", value)):
            found.extend(_nulls_in(item, path=f"{path}[{index_item}]"))
        return found
    return []


class TestProblemViews:
    def test_the_caller_view_has_no_diagnostics_and_the_operator_view_has_them(self) -> None:
        error = _MisconfiguredError(ProblemViewsTestData.OPERATOR_MESSAGE).with_params(component=ProblemViewsTestData.COMPONENT)

        operator = error.to_problem(view=ProblemView.OPERATOR)
        caller = error.to_problem(view=ProblemView.CALLER)

        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "_MisconfiguredError"
        assert operator.diagnostics.message == ProblemViewsTestData.OPERATOR_MESSAGE
        assert caller.diagnostics is None
        assert "diagnostics" not in caller.to_wire()
        assert ProblemViewsTestData.OPERATOR_MESSAGE not in str(caller.to_wire())
        # The same code, domain, verdict and sentence in both views.
        assert (caller.code, caller.domain, caller.retry, caller.detail) == (operator.code, operator.domain, operator.retry, operator.detail)
        assert caller.detail == error_code_spec(CoreCode.RUNTIME_MISCONFIGURED).detail

    def test_an_operator_code_aims_its_step_at_the_reader(self) -> None:
        """The operator reads the actor's step; the caller, who cannot fix the deployment, reads the other one."""
        error = _MisconfiguredError(ProblemViewsTestData.OPERATOR_MESSAGE).with_params(component=ProblemViewsTestData.COMPONENT)

        operator = error.to_problem(view=ProblemView.OPERATOR)
        caller = error.to_problem(view=ProblemView.CALLER)

        assert operator.next_step.kind == StepKind.FIX_CONFIGURATION
        assert operator.next_step.detail == f"Set or correct the configuration of '{ProblemViewsTestData.COMPONENT}', then restart the runtime."
        assert caller.next_step.kind == StepKind.REPORT
        assert caller.next_step.detail == "Report this to whoever runs the runtime."

    def test_an_operator_only_parameter_rides_the_operator_diagnostics_alone(self) -> None:
        error = _MisconfiguredError(ProblemViewsTestData.OPERATOR_MESSAGE).with_params(component=ProblemViewsTestData.COMPONENT)

        operator = error.to_problem(view=ProblemView.OPERATOR)
        caller = error.to_problem(view=ProblemView.CALLER)

        assert operator.params is None
        assert operator.diagnostics is not None
        assert operator.diagnostics.params == {"component": ProblemViewsTestData.COMPONENT}
        assert caller.params is None
        assert ProblemViewsTestData.COMPONENT not in str(caller.to_wire())

    def test_the_caller_view_of_the_operator_view_is_the_caller_view(self) -> None:
        for error in (
            _MisconfiguredError(ProblemViewsTestData.OPERATOR_MESSAGE).with_params(component=ProblemViewsTestData.COMPONENT),
            _TemplateRefusalError("the template does not parse").with_params(pipe="summarize", template="prompt", finding="unexpected '}'"),
        ):
            projected = caller_view_of(problem=error.to_problem(view=ProblemView.OPERATOR))
            assert projected.to_wire() == error.to_problem(view=ProblemView.CALLER).to_wire()

    def test_the_detail_is_rendered_from_the_code_and_its_parameters(self) -> None:
        error = _TemplateRefusalError("the raise site's own words").with_params(pipe="summarize", template="prompt", finding="unexpected '}'")

        caller = error.to_problem(view=ProblemView.CALLER)

        assert caller.detail == "The template 'prompt' of pipe 'summarize' is invalid (unexpected '}')."
        assert caller.params is not None
        assert caller.params.as_wire() == {"pipe": "summarize", "template": "prompt", "finding": "unexpected '}'"}
        assert "the raise site's own words" not in str(caller.to_wire())

    def test_a_template_missing_a_parameter_falls_back_on_the_title(self, caplog: pytest.LogCaptureFixture) -> None:
        """Rendering is total: a missing parameter costs the sentence, never the problem, and the raise site is logged."""
        error = _TemplateRefusalError("no parameters given")

        with caplog.at_level(logging.WARNING, logger="pipelex.errors.problem"):
            caller = error.to_problem(view=ProblemView.CALLER)

        spec = error_code_spec(CoreCode.METHOD_TEMPLATE_INVALID)
        assert caller.detail == spec.title
        assert caller.next_step.kind == spec.actor_step
        assert caller.next_step.detail
        assert any(record.getMessage() == "A problem's sentence could not be rendered from its template" for record in caplog.records)

    def test_an_undeclared_or_mistyped_parameter_is_dropped(self, caplog: pytest.LogCaptureFixture) -> None:
        error = _TemplateRefusalError("refused").with_params(pipe="summarize", template="prompt", finding="bad", undeclared="secret value")

        with caplog.at_level(logging.WARNING, logger="pipelex.errors.problem"):
            caller = error.to_problem(view=ProblemView.CALLER)

        assert caller.params is not None
        assert "undeclared" not in caller.params.as_wire()
        assert "secret value" not in str(caller.to_wire())
        assert any(record.getMessage() == "An error gives a parameter its code does not declare" for record in caplog.records)

    @pytest.mark.parametrize("view", list(ProblemView))
    def test_no_problem_holds_a_null_member(self, view: ProblemView) -> None:
        """Every code, in every view, with no parameter given: no member at any depth is written as null."""
        for code in _all_codes():
            problem = make_problem(code=code, view=view)
            assert _nulls_in(problem.to_wire()) == [], code
            assert _nulls_in(problem.model_dump(mode="json")) == [], code
            nested = _NodeHolder(error=problem).model_dump(mode="json")
            assert _nulls_in(nested["error"]) == [], code

    @pytest.mark.parametrize("view", list(ProblemView))
    def test_a_problem_built_from_a_rich_error_holds_no_null_member(self, view: ProblemView) -> None:
        error = LLMCompletionError(
            ProblemViewsTestData.OPERATOR_MESSAGE,
            error_category=InferenceErrorCategory.CONFIGURATION,
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.OPENAI, sdk_exception_type="AuthenticationError", status_code=401, message="invalid key"
            ),
        )
        error.model_handle = "gpt-4o-mini"

        problem = error.to_problem(view=view, request_id="req-1", pipeline_run_id="run-1")

        assert _nulls_in(problem.to_wire()) == []

    def test_a_message_is_bounded(self) -> None:
        """An oversized exception message is capped, its head kept, in the operator's diagnostics."""
        oversized = "Validation failed: " + "x" * (MAX_PROBLEM_TEXT_LENGTH * 50)
        error = LLMCompletionError(oversized, error_category=InferenceErrorCategory.UNKNOWN)

        operator = error.to_problem(view=ProblemView.OPERATOR)

        assert operator.diagnostics is not None
        message = operator.diagnostics.message
        assert len(message) <= MAX_PROBLEM_TEXT_LENGTH
        assert message.startswith("Validation failed: ")
        assert message.endswith(TRUNCATION_MARKER)

    def test_a_provider_message_and_a_text_parameter_are_bounded(self) -> None:
        oversized = "y" * (MAX_PROBLEM_TEXT_LENGTH * 3)
        provider_error = LLMCompletionError(
            "provider refused",
            error_category=InferenceErrorCategory.CONFIGURATION,
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.OPENAI, sdk_exception_type="BadRequestError", status_code=400, message=oversized
            ),
        )
        template_error = _TemplateRefusalError("refused").with_params(pipe="summarize", template="prompt", finding=oversized)

        operator = provider_error.to_problem(view=ProblemView.OPERATOR)
        caller = template_error.to_problem(view=ProblemView.CALLER)

        assert operator.diagnostics is not None
        assert operator.diagnostics.provider is not None
        assert operator.diagnostics.provider.message is not None
        assert len(operator.diagnostics.provider.message) <= MAX_PROBLEM_TEXT_LENGTH
        assert caller.params is not None
        assert len(caller.params.as_wire()["finding"]) <= MAX_PROBLEM_TEXT_LENGTH

    def test_an_inference_failure_keeps_a_next_step_in_the_caller_view(self) -> None:
        """No view drops the step: a classified inference failure tells its caller what to do."""
        error = LLMCompletionError(
            "provider said: invalid key sk-...",
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(kind=UserActionKind.CHECK_CREDENTIALS, detail="Verify the API key."),
        )

        caller = error.to_problem(view=ProblemView.CALLER)

        # A configuration failure is the operator's to fix, so its caller is told to report it.
        assert caller.code == CoreCode.RUNTIME_MISCONFIGURED
        assert caller.next_step.kind == StepKind.REPORT
        assert caller.next_step.detail == "Report this to whoever runs the runtime."
        assert "sk-" not in str(caller.to_wire())

    def test_no_step_points_at_text_a_caller_cannot_see(self) -> None:
        """Every step of every code stands alone: none sends its reader to an error message the view may not show."""
        for code in _all_codes():
            for view in ProblemView:
                step_detail = make_problem(code=code, view=view).next_step.detail.lower()
                for phrase in ProblemViewsTestData.HIDDEN_TEXT_PHRASES:
                    assert phrase not in step_detail, (code, view, step_detail)

    def test_a_gateway_refusal_reads_without_the_provider_text(self) -> None:
        """The provider's specifics stay the operator's, and the caller's step and detail still read in full."""
        error = LLMCompletionError(
            ProblemViewsTestData.GATEWAY_MESSAGE,
            error_category=InferenceErrorCategory.CONFIGURATION,
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.GATEWAY,
                sdk_exception_type="BadRequestError",
                status_code=400,
                message=ProblemViewsTestData.GATEWAY_PROVIDER_TEXT,
            ),
        )
        error.model_handle = "acme/large"

        caller = error.to_problem(view=ProblemView.CALLER)
        operator = error.to_problem(view=ProblemView.OPERATOR)

        assert ProblemViewsTestData.GATEWAY_PROVIDER_TEXT not in str(caller.to_wire())
        assert caller.detail
        assert caller.next_step.detail
        assert operator.diagnostics is not None
        assert operator.diagnostics.provider is not None
        assert operator.diagnostics.provider.message == ProblemViewsTestData.GATEWAY_PROVIDER_TEXT

    def test_an_unusable_retry_delay_is_left_out(self) -> None:
        for delay in (float("inf"), float("nan"), -1.0):
            problem = make_problem(code=CoreCode.PROVIDER_RATE_LIMITED, view=ProblemView.CALLER, retry_after=delay)
            assert problem.retry_after is None
        assert make_problem(code=CoreCode.PROVIDER_RATE_LIMITED, view=ProblemView.CALLER, retry_after=3.5).retry_after == 3.5
        # A code whose verdict is not `yes` never carries a delay.
        assert make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.CALLER, retry_after=3.5).retry_after is None

    def test_the_metadata_view_holds_no_sentence(self) -> None:
        error = _TemplateRefusalError("refused").with_params(pipe="summarize", template="prompt", finding="unexpected '}'")
        problem = error.to_problem(view=ProblemView.OPERATOR, request_id="req-1", pipeline_run_id="run-1")

        metadata = problem_metadata(problem=problem).to_wire()

        assert metadata["code"] == "method.template_invalid"
        assert metadata["request_id"] == "req-1"
        assert metadata["pipeline_run_id"] == "run-1"
        assert "summarize" not in str(metadata)
        assert problem.detail not in str(metadata)
        assert problem.next_step.detail not in str(metadata)
