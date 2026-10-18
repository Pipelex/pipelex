from __future__ import annotations

import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain

from pipelex.cogt.exceptions import (
    CompletionTruncationLimit,
    InferenceErrorCategory,
    LLMCompletionError,
    LLMCompletionRefusedError,
    LLMCompletionTruncatedError,
    find_inference_error_category_in_chain,
)
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.errors.error_codes import ErrorCode, error_code_spec
from pipelex.errors.problem import ProblemView
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.helpers.completion_stop import STOP_TEST_PARTIAL_TEXT

TRUNCATED_MESSAGE = (
    "The model 'claude-5-sonnet' was cut off before it finished the text of pipe 'ui_designer' "
    "(stop reason 'max_tokens', 4096 output tokens used, max_tokens set to 4096), so the text is incomplete. "
    "Raise the pipe's max_tokens, or shorten its input."
)
NO_MAX_TOKENS_NEXT_STEP = "Set the pipe's max_tokens up to the model's limit, lower its reasoning effort, or shorten its input."
CONTEXT_WINDOW_NEXT_STEP = "Shorten the pipe's input, lower its reasoning effort, or choose a model with a larger context window."
CONTEXT_WINDOW_MESSAGE = (
    "The model 'claude-5-sonnet' filled its context window before it finished the text of pipe 'ui_designer' "
    "(stop reason 'model_context_window_exceeded', 812 output tokens used, max_tokens set to 4096), so the text is incomplete. "
    f"{CONTEXT_WINDOW_NEXT_STEP}"
)
REFUSED_MESSAGE = (
    "The model 'claude-5-sonnet' declined to finish the text of pipe 'ui_designer', or a content filter stopped it "
    "(stop reason 'content_filtered'), so the text cannot be used. Revise the pipe's prompt or its input."
)


def _truncated_error() -> LLMCompletionTruncatedError:
    return LLMCompletionTruncatedError(
        model_handle="claude-5-sonnet",
        stop_reason="max_tokens",
        truncation_limit=CompletionTruncationLimit.MAX_TOKENS,
        pipe_code="ui_designer",
        max_tokens=4096,
        output_tokens=4096,
    )


def _context_window_error() -> LLMCompletionTruncatedError:
    return LLMCompletionTruncatedError(
        model_handle="claude-5-sonnet",
        stop_reason="model_context_window_exceeded",
        truncation_limit=CompletionTruncationLimit.CONTEXT_WINDOW,
        pipe_code="ui_designer",
        max_tokens=4096,
        output_tokens=812,
    )


def _refused_error() -> LLMCompletionRefusedError:
    return LLMCompletionRefusedError(model_handle="claude-5-sonnet", stop_reason="content_filtered", pipe_code="ui_designer")


class TestLLMCompletionStopErrors:
    def test_the_truncation_names_the_pipe_model_stop_counts_and_next_step(self) -> None:
        error = _truncated_error()

        assert error.message == TRUNCATED_MESSAGE
        assert error.user_action is not None
        assert error.user_action.kind == UserActionKind.CHANGE_INPUT
        assert error.user_action.detail == "Raise the pipe's max_tokens, or shorten its input."

    def test_a_cut_with_no_max_tokens_sent_advises_setting_one_rather_than_raising_it(self) -> None:
        """The provider's default cut the text, so there is no max_tokens of the pipe's to raise: the advice is to set one."""
        error = LLMCompletionTruncatedError(
            model_handle="gpt-test",
            stop_reason="length",
            truncation_limit=CompletionTruncationLimit.MAX_TOKENS,
            pipe_code="ui_designer",
            output_tokens=16384,
        )

        assert error.message == (
            "The model 'gpt-test' was cut off before it finished the text of pipe 'ui_designer' "
            "(stop reason 'length', 16384 output tokens used, no max_tokens sent), so the text is incomplete. "
            f"{NO_MAX_TOKENS_NEXT_STEP}"
        )
        assert error.user_action is not None
        assert error.user_action.kind == UserActionKind.CHANGE_INPUT
        assert error.user_action.detail == NO_MAX_TOKENS_NEXT_STEP
        assert "Raise" not in error.message

    def test_a_context_window_stop_advises_a_shorter_input_never_a_higher_max_tokens(self) -> None:
        """The input and the output filled the window together, so a higher max_tokens cannot lift it."""
        error = _context_window_error()

        assert error.message == CONTEXT_WINDOW_MESSAGE
        assert error.user_action is not None
        assert error.user_action.kind == UserActionKind.CHANGE_INPUT
        assert error.user_action.detail == CONTEXT_WINDOW_NEXT_STEP
        assert "Raise" not in error.message

    def test_the_refusal_names_the_pipe_model_stop_and_next_step(self) -> None:
        error = _refused_error()

        assert error.message == REFUSED_MESSAGE
        assert error.user_action is not None
        assert error.user_action.kind == UserActionKind.CHANGE_INPUT
        assert error.user_action.detail == "Revise the pipe's prompt or its input."

    def test_without_a_pipe_or_counts_the_messages_still_read_as_sentences(self) -> None:
        truncated = LLMCompletionTruncatedError(
            model_handle="gpt-test", stop_reason="length", truncation_limit=CompletionTruncationLimit.MAX_TOKENS, max_tokens=2048
        )
        truncated_by_default = LLMCompletionTruncatedError(
            model_handle="gpt-test", stop_reason="length", truncation_limit=CompletionTruncationLimit.MAX_TOKENS
        )
        context_window = LLMCompletionTruncatedError(
            model_handle="mistral-test", stop_reason="model_length", truncation_limit=CompletionTruncationLimit.CONTEXT_WINDOW
        )
        refused = LLMCompletionRefusedError(model_handle="gpt-test", stop_reason="refusal")

        assert truncated.message == (
            "The model 'gpt-test' was cut off before it finished its text (stop reason 'length', max_tokens set to 2048), "
            "so the text is incomplete. Raise max_tokens, or shorten the input."
        )
        assert truncated_by_default.message == (
            "The model 'gpt-test' was cut off before it finished its text (stop reason 'length', no max_tokens sent), "
            "so the text is incomplete. Set max_tokens up to the model's limit, lower the reasoning effort, or shorten the input."
        )
        assert context_window.message == (
            "The model 'mistral-test' filled its context window before it finished its text (stop reason 'model_length'), "
            "so the text is incomplete. Shorten the input, lower the reasoning effort, or choose a model with a larger context window."
        )
        assert refused.message == (
            "The model 'gpt-test' declined to finish its text, or a content filter stopped it (stop reason 'refusal'), "
            "so the text cannot be used. Revise the prompt or the input."
        )

    @pytest.mark.builds_problems_without_required_params(
        reason="a context-window stop signal carries neither the prompt's size nor the window's, the counts of model.context_exceeded"
    )
    @pytest.mark.parametrize(
        ("error_class", "error", "expected_code", "expected_domain", "user_action_detail"),
        [
            (
                "LLMCompletionTruncatedError",
                _truncated_error(),
                CoreCode.MODEL_OUTPUT_TRUNCATED,
                ProblemDomain.METHOD,
                "Raise the pipe's max_tokens, or shorten its input.",
            ),
            ("LLMCompletionTruncatedError", _context_window_error(), CoreCode.MODEL_CONTEXT_EXCEEDED, ProblemDomain.INPUT, CONTEXT_WINDOW_NEXT_STEP),
            (
                "LLMCompletionRefusedError",
                _refused_error(),
                CoreCode.MODEL_CONTENT_REFUSED,
                ProblemDomain.INPUT,
                "Revise the pipe's prompt or its input.",
            ),
        ],
    )
    def test_the_problem_carries_the_fields_an_agent_branches_on(
        self,
        error_class: str,
        error: LLMCompletionError,
        expected_code: ErrorCode,
        expected_domain: ProblemDomain,
        user_action_detail: str,
    ) -> None:
        """A content error no retry clears, its code and domain its stop's, its class and model for the operator, its advice a change of input."""
        assert isinstance(error, LLMCompletionError)
        problem = error.to_problem(view=ProblemView.OPERATOR)

        assert problem.code == expected_code
        assert problem.domain == expected_domain
        assert problem.is_retryable is False
        assert error_code_spec(expected_code).status == 422
        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == error_class
        assert problem.diagnostics.model == "claude-5-sonnet"
        assert find_inference_error_category_in_chain(error) == InferenceErrorCategory.CONTENT
        advice = error.advised_action()
        assert advice is not None
        assert advice.kind == UserActionKind.CHANGE_INPUT
        assert advice.detail == user_action_detail

    @pytest.mark.builds_problems_without_required_params(
        reason="a context-window stop signal carries neither the prompt's size nor the window's, the counts of model.context_exceeded"
    )
    @pytest.mark.parametrize("error", [_truncated_error(), _context_window_error(), _refused_error()])
    def test_the_caller_reads_the_model_without_the_partial_text(self, error: LLMCompletionError) -> None:
        """The caller's problem names the model in the code's parameters, and no view carries the partial text."""
        caller = error.to_problem(view=ProblemView.CALLER)
        operator = error.to_problem(view=ProblemView.OPERATOR)

        assert caller.params is not None
        assert caller.params.as_wire()["model"] == "claude-5-sonnet"
        assert caller.is_retryable is False
        assert caller.diagnostics is None
        assert operator.diagnostics is not None
        assert operator.diagnostics.message == error.message
        assert STOP_TEST_PARTIAL_TEXT not in str(caller.to_wire())
        assert STOP_TEST_PARTIAL_TEXT not in str(operator.to_wire())

    def test_a_run_failure_located_at_the_pipe_reports_the_truncation(self) -> None:
        """The pipe router's located problem keeps the truncation's code, its class and message for the operator, and the pipe's location."""
        truncation = _truncated_error()
        located = PipeRouterError.make_located(
            failure=truncation, run_mode=PipeRunMode.LIVE, pipe_code="ui_designer", output_name=None, pipe_stack=["flow", "ui_designer"]
        )
        located.__cause__ = truncation

        problem = located.to_problem(view=ProblemView.OPERATOR)

        assert problem.code == CoreCode.MODEL_OUTPUT_TRUNCATED
        assert problem.domain == ProblemDomain.METHOD
        assert problem.is_retryable is False
        assert problem.location is not None
        assert problem.location.as_wire() == {"pipe": "ui_designer", "path": ["flow", "ui_designer"]}
        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == "LLMCompletionTruncatedError"
        assert problem.diagnostics.message == TRUNCATED_MESSAGE

    @pytest.mark.builds_problems_without_required_params(
        reason="a context-window stop signal carries neither the prompt's size nor the window's, the counts of model.context_exceeded"
    )
    def test_a_context_window_stop_names_the_bound_it_passed(self) -> None:
        """The stop signal names the bound, the context window, and neither the prompt's size nor the window's."""
        caller = _context_window_error().to_problem(view=ProblemView.CALLER)

        assert caller.code == CoreCode.MODEL_CONTEXT_EXCEEDED
        assert caller.params is not None
        assert caller.params.as_wire() == {"model": "claude-5-sonnet", "limit": "context_window"}
