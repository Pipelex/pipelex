from __future__ import annotations

import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain

from pipelex.cogt.exceptions import (
    CompletionOutputKind,
    CompletionTruncationLimit,
    InferenceErrorCategory,
    LLMCompletionError,
    LLMCompletionRefusedError,
    LLMCompletionTruncatedError,
    MaxTokensCeiling,
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
        output_kind=CompletionOutputKind.TEXT,
        pipe_code="ui_designer",
        max_tokens=4096,
        output_tokens=4096,
    )


def _context_window_error() -> LLMCompletionTruncatedError:
    return LLMCompletionTruncatedError(
        model_handle="claude-5-sonnet",
        stop_reason="model_context_window_exceeded",
        truncation_limit=CompletionTruncationLimit.CONTEXT_WINDOW,
        output_kind=CompletionOutputKind.TEXT,
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
            output_kind=CompletionOutputKind.TEXT,
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

    def test_a_cut_structured_output_is_named_a_structured_output_not_a_text(self) -> None:
        error = LLMCompletionTruncatedError(
            model_handle="claude-5-sonnet",
            stop_reason="max_tokens",
            truncation_limit=CompletionTruncationLimit.MAX_TOKENS,
            output_kind=CompletionOutputKind.STRUCTURED,
            pipe_code="ui_designer",
            max_tokens=4096,
            output_tokens=4096,
        )
        without_pipe = LLMCompletionTruncatedError(
            model_handle="gpt-test",
            stop_reason="length",
            truncation_limit=CompletionTruncationLimit.MAX_TOKENS,
            output_kind=CompletionOutputKind.STRUCTURED,
            max_tokens=2048,
        )

        assert error.message == (
            "The model 'claude-5-sonnet' was cut off before it finished the structured output of pipe 'ui_designer' "
            "(stop reason 'max_tokens', 4096 output tokens used, max_tokens set to 4096), so the structured output is incomplete. "
            "Raise the pipe's max_tokens, or shorten its input."
        )
        assert without_pipe.message == (
            "The model 'gpt-test' was cut off before it finished its structured output (stop reason 'length', max_tokens set to 2048), "
            "so the structured output is incomplete. Raise max_tokens, or shorten the input."
        )
        assert "text" not in error.message
        assert error.output_kind == CompletionOutputKind.STRUCTURED

    def test_a_limit_lowered_to_fit_the_timeout_is_never_advised_raised(self) -> None:
        """A higher max_tokens is lowered to the same ceiling, so neither the message nor the action asks for one."""
        next_step = "Lower the pipe's reasoning effort, or ask it for a smaller output, since a higher max_tokens is lowered the same way."
        error = LLMCompletionTruncatedError(
            model_handle="claude-5-sonnet",
            stop_reason="max_tokens",
            truncation_limit=CompletionTruncationLimit.MAX_TOKENS,
            output_kind=CompletionOutputKind.STRUCTURED,
            pipe_code="ui_designer",
            max_tokens=42666,
            output_tokens=42666,
            max_tokens_ceiling=MaxTokensCeiling(requested_max_tokens=64000, timeout_seconds=1200),
        )

        assert error.message == (
            "The model 'claude-5-sonnet' was cut off before it finished the structured output of pipe 'ui_designer' "
            "(stop reason 'max_tokens', 42666 output tokens used, max_tokens set to 42666), so the structured output is incomplete. "
            f"Its max_tokens was lowered from 64000 to 42666 to fit the call's 1200-second timeout. {next_step}"
        )
        assert error.user_action is not None
        assert error.user_action.kind == UserActionKind.CHANGE_INPUT
        assert error.user_action.detail == next_step
        assert "Raise" not in error.message
        assert error.max_tokens_ceiling == MaxTokensCeiling(requested_max_tokens=64000, timeout_seconds=1200)

    def test_the_refusal_names_the_pipe_model_stop_and_next_step(self) -> None:
        error = _refused_error()

        assert error.message == REFUSED_MESSAGE
        assert error.user_action is not None
        assert error.user_action.kind == UserActionKind.CHANGE_INPUT
        assert error.user_action.detail == "Revise the pipe's prompt or its input."

    def test_without_a_pipe_or_counts_the_messages_still_read_as_sentences(self) -> None:
        truncated = LLMCompletionTruncatedError(
            model_handle="gpt-test",
            stop_reason="length",
            truncation_limit=CompletionTruncationLimit.MAX_TOKENS,
            output_kind=CompletionOutputKind.TEXT,
            max_tokens=2048,
        )
        truncated_by_default = LLMCompletionTruncatedError(
            model_handle="gpt-test",
            stop_reason="length",
            truncation_limit=CompletionTruncationLimit.MAX_TOKENS,
            output_kind=CompletionOutputKind.TEXT,
        )
        context_window = LLMCompletionTruncatedError(
            model_handle="mistral-test",
            stop_reason="model_length",
            truncation_limit=CompletionTruncationLimit.CONTEXT_WINDOW,
            output_kind=CompletionOutputKind.TEXT,
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
