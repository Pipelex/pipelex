from __future__ import annotations

import typing
from typing import TYPE_CHECKING

import pytest
from anthropic.types import StopReason
from google.genai.types import FinishReason
from mistralai.client.models.chatcompletionchoice import ChatCompletionChoiceFinishReason
from openai.types.chat.chat_completion import Choice
from openai.types.responses.response import IncompleteDetails
from types_aiobotocore_bedrock_runtime.literals import StopReasonType

from pipelex.cogt.exceptions import LLMCompletionRefusedError, LLMCompletionTruncatedError
from pipelex.cogt.llm import completion_stop
from pipelex.cogt.llm.completion_stop import (
    ANTHROPIC_STOP_REASONS,
    BEDROCK_CONVERSE_STOP_REASONS,
    GEMINI_FINISH_REASONS,
    MISTRAL_FINISH_REASONS,
    OPENAI_CHAT_FINISH_REASONS,
    OPENAI_RESPONSES_INCOMPLETE_REASONS,
    STOP_REASON_VOCABULARIES,
    CompletionStopOutcome,
    classify_responses_stop,
    classify_stop_reason,
    raise_for_completion_stop,
)
from tests.unit.pipelex.cogt.llm.test_data import CompletionStopTestData

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _literal_values(annotation: object) -> set[str]:
    """The string values of a `Literal`, looked for inside an `Optional` or a union with an open string type."""
    values: set[str] = set()
    for argument in typing.get_args(annotation):
        if isinstance(argument, str):
            values.add(argument)
        else:
            values.update(_literal_values(argument))
    return values


class TestCompletionStop:
    @pytest.mark.parametrize(("_topic", "stop_reason", "expected_outcome"), CompletionStopTestData.STOP_REASON_CASES)
    def test_each_vocabulary_is_classified(self, _topic: str, stop_reason: str, expected_outcome: CompletionStopOutcome) -> None:
        assert classify_stop_reason(stop_reason=stop_reason, model_handle="test-model") == expected_outcome

    def test_a_gemini_value_is_read_whatever_its_case(self) -> None:
        assert classify_stop_reason(stop_reason="max_tokens", model_handle="gemini-test") == CompletionStopOutcome.TRUNCATED
        assert classify_stop_reason(stop_reason="Safety", model_handle="gemini-test") == CompletionStopOutcome.REFUSED

    def test_an_unknown_value_is_logged_and_taken_as_normal(self, mocker: MockerFixture) -> None:
        """A value no vocabulary knows warns, naming the model and the value, and fails nothing."""
        warning = mocker.patch.object(completion_stop.log, "warning")

        outcome = classify_stop_reason(stop_reason="brand_new_stop", model_handle="claude-test")

        assert outcome == CompletionStopOutcome.NORMAL
        warning.assert_called_once_with(
            "An LLM stop reason was not recognized, so it was taken as normal",
            fields={"model_handle": "claude-test", "stop_reason": "brand_new_stop"},
        )

    def test_a_missing_value_is_normal_without_a_word(self, mocker: MockerFixture) -> None:
        warning = mocker.patch.object(completion_stop.log, "warning")

        assert classify_stop_reason(stop_reason=None, model_handle="test-model") == CompletionStopOutcome.NORMAL
        warning.assert_not_called()

    @pytest.mark.parametrize(("_topic", "status", "incomplete_reason", "expected_outcome"), CompletionStopTestData.RESPONSES_CASES)
    def test_a_responses_answer_is_classified(
        self, _topic: str, status: str | None, incomplete_reason: str | None, expected_outcome: CompletionStopOutcome
    ) -> None:
        outcome = classify_responses_stop(status=status, incomplete_reason=incomplete_reason, model_handle="gpt-test")
        assert outcome == expected_outcome

    def test_an_incomplete_answer_with_an_unknown_reason_is_logged_and_taken_as_normal(self, mocker: MockerFixture) -> None:
        warning = mocker.patch.object(completion_stop.log, "warning")

        outcome = classify_responses_stop(status="incomplete", incomplete_reason="brand_new_reason", model_handle="gpt-test")

        assert outcome == CompletionStopOutcome.NORMAL
        warning.assert_called_once_with(
            "An LLM stop reason was not recognized, so it was taken as normal",
            fields={"model_handle": "gpt-test", "stop_reason": "incomplete: brand_new_reason"},
        )

    def test_the_vocabularies_agree_on_every_shared_value(self) -> None:
        """Read as one table, no two vocabularies may read the same case-folded value differently."""
        readings: dict[str, set[CompletionStopOutcome]] = {}
        for vocabulary in STOP_REASON_VOCABULARIES:
            for value, outcome in vocabulary.items():
                readings.setdefault(value.casefold(), set()).add(outcome)
        conflicting = {value: outcomes for value, outcomes in readings.items() if len(outcomes) > 1}
        assert not conflicting

    def test_each_vocabulary_covers_its_sdk_type(self) -> None:
        """Each table holds every value its provider SDK's own type lists, plus only the additions it documents."""
        assert set(OPENAI_CHAT_FINISH_REASONS) == _literal_values(Choice.model_fields["finish_reason"].annotation) | {"refusal"}
        assert set(ANTHROPIC_STOP_REASONS) == _literal_values(StopReason) | {"model_context_window_exceeded"}
        assert set(BEDROCK_CONVERSE_STOP_REASONS) == _literal_values(StopReasonType)
        assert set(GEMINI_FINISH_REASONS) == {member.value for member in FinishReason}
        assert set(MISTRAL_FINISH_REASONS) == _literal_values(ChatCompletionChoiceFinishReason)
        assert set(OPENAI_RESPONSES_INCOMPLETE_REASONS) == _literal_values(IncompleteDetails.model_fields["reason"].annotation)

    def test_a_normal_stop_raises_nothing(self) -> None:
        raise_for_completion_stop(
            outcome=CompletionStopOutcome.NORMAL,
            stop_reason="end_turn",
            model_handle="claude-test",
            pipe_code="summarize",
            max_tokens=4096,
            output_tokens=12,
        )

    def test_a_truncated_stop_raises_the_truncation(self) -> None:
        with pytest.raises(LLMCompletionTruncatedError) as exc_info:
            raise_for_completion_stop(
                outcome=CompletionStopOutcome.TRUNCATED,
                stop_reason="max_tokens",
                model_handle="claude-test",
                pipe_code="summarize",
                max_tokens=4096,
                output_tokens=4096,
            )
        assert exc_info.value.stop_reason == "max_tokens"
        assert exc_info.value.max_tokens == 4096
        assert exc_info.value.output_tokens == 4096

    def test_a_refused_stop_raises_the_refusal(self) -> None:
        with pytest.raises(LLMCompletionRefusedError) as exc_info:
            raise_for_completion_stop(
                outcome=CompletionStopOutcome.REFUSED,
                stop_reason="content_filtered",
                model_handle="claude-test",
                pipe_code="summarize",
                max_tokens=4096,
                output_tokens=0,
            )
        assert exc_info.value.stop_reason == "content_filtered"
        assert exc_info.value.pipe_code == "summarize"
