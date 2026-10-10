from __future__ import annotations

import pytest

from pipelex.base_exceptions import DisclosureMode, ErrorDomain
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMCompletionRefusedError, LLMCompletionTruncatedError
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.helpers.completion_stop import STOP_TEST_PARTIAL_TEXT

TRUNCATED_MESSAGE = (
    "The model 'claude-5-sonnet' was cut off before it finished the text of pipe 'ui_designer' "
    "(stop reason 'max_tokens', 4096 output tokens used, max_tokens set to 4096), so the text is incomplete. "
    "Raise the pipe's max_tokens, or shorten its input."
)
REFUSED_MESSAGE = (
    "The model 'claude-5-sonnet' declined to finish the text of pipe 'ui_designer', or a content filter stopped it "
    "(stop reason 'content_filtered'), so the text cannot be used. Revise the pipe's prompt or its input."
)


def _truncated_error() -> LLMCompletionTruncatedError:
    return LLMCompletionTruncatedError(
        model_handle="claude-5-sonnet", stop_reason="max_tokens", pipe_code="ui_designer", max_tokens=4096, output_tokens=4096
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

    def test_the_refusal_names_the_pipe_model_stop_and_next_step(self) -> None:
        error = _refused_error()

        assert error.message == REFUSED_MESSAGE
        assert error.user_action is not None
        assert error.user_action.kind == UserActionKind.CHANGE_INPUT
        assert error.user_action.detail == "Revise the pipe's prompt or its input."

    def test_without_a_pipe_or_counts_the_messages_still_read_as_sentences(self) -> None:
        truncated = LLMCompletionTruncatedError(model_handle="gpt-test", stop_reason="length")
        refused = LLMCompletionRefusedError(model_handle="gpt-test", stop_reason="refusal")

        assert truncated.message == (
            "The model 'gpt-test' was cut off before it finished its text (stop reason 'length'), so the text is incomplete. "
            "Raise max_tokens, or shorten the input."
        )
        assert refused.message == (
            "The model 'gpt-test' declined to finish its text, or a content filter stopped it (stop reason 'refusal'), "
            "so the text cannot be used. Revise the prompt or the input."
        )

    @pytest.mark.parametrize(
        ("error_type", "error", "user_action_detail"),
        [
            ("LLMCompletionTruncatedError", _truncated_error(), "Raise the pipe's max_tokens, or shorten its input."),
            ("LLMCompletionRefusedError", _refused_error(), "Revise the pipe's prompt or its input."),
        ],
    )
    def test_the_report_carries_the_fields_an_agent_branches_on(self, error_type: str, error: LLMCompletionError, user_action_detail: str) -> None:
        """A content error in the input domain, not retryable, its next step a change of input, its type its own."""
        assert isinstance(error, LLMCompletionError)
        report = error.to_error_report()

        assert report.error_type == error_type
        assert report.error_category == InferenceErrorCategory.CONTENT
        assert report.error_domain == ErrorDomain.INPUT
        assert report.retryable is False
        assert report.model == "claude-5-sonnet"
        assert report.user_action is not None
        assert report.user_action.kind == UserActionKind.CHANGE_INPUT
        assert report.user_action.detail == user_action_detail
        assert report.http_status == 422

    @pytest.mark.parametrize("error", [_truncated_error(), _refused_error()])
    def test_the_message_survives_strict_disclosure_without_the_partial_text(self, error: LLMCompletionError) -> None:
        payload = error.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)

        assert payload["message"] == error.message
        assert payload["user_action"]["kind"] == "change_input"
        assert payload["error_domain"] == "input"
        assert payload["retryable"] is False
        assert STOP_TEST_PARTIAL_TEXT not in payload["message"]

    def test_a_run_failure_located_at_the_pipe_reports_the_truncation(self) -> None:
        """The pipe router's located report keeps the truncation's identity, classification and caller-facing message."""
        truncation = _truncated_error()
        located = PipeRouterError.make_located(
            failure=truncation, run_mode=PipeRunMode.LIVE, pipe_code="ui_designer", output_name=None, pipe_stack=["flow", "ui_designer"]
        )
        located.__cause__ = truncation

        report = located.to_error_report()

        assert report.error_type == "LLMCompletionTruncatedError"
        assert report.message == f"Pipe 'ui_designer' failed (flow → ui_designer): {TRUNCATED_MESSAGE}"
        assert report.retryable is False
        assert report.error_domain == ErrorDomain.INPUT
        assert report.to_dict(disclosure_mode=DisclosureMode.STRICT)["message"] == report.message
