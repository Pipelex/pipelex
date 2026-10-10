from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mistralai.client.models import AssistantMessage, ChatCompletionChoice, ChatCompletionResponse, UsageInfo
from mistralai.client.types import UnrecognizedStr

from pipelex.cogt.exceptions import LLMCompletionRefusedError, LLMCompletionTruncatedError
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from tests.helpers.completion_stop import STOP_TEST_PARTIAL_TEXT, STOP_TEST_PIPE_CODE, make_text_llm_job
from tests.helpers.mistral_request import make_worker

if TYPE_CHECKING:
    from mistralai.client.models.chatcompletionchoice import ChatCompletionChoiceFinishReason
    from pytest_mock import MockerFixture


def _response(*, finish_reason: ChatCompletionChoiceFinishReason, text: str) -> ChatCompletionResponse:
    return ChatCompletionResponse(
        id="cmpl_test",
        object="chat.completion",
        model="mistral-test",
        created=0,
        usage=UsageInfo(prompt_tokens=20, completion_tokens=4096, total_tokens=4116),
        choices=[ChatCompletionChoice(index=0, finish_reason=finish_reason, message=AssistantMessage(content=text))],
    )


@pytest.mark.asyncio(loop_scope="class")
class TestMistralTextStop:
    @pytest.mark.parametrize(
        ("finish_reason", "text"),
        [
            ("length", STOP_TEST_PARTIAL_TEXT),
            ("length", ""),
            ("model_length", STOP_TEST_PARTIAL_TEXT),
        ],
    )
    async def test_a_text_cut_at_its_length_raises_the_truncation(
        self, mocker: MockerFixture, finish_reason: ChatCompletionChoiceFinishReason, text: str
    ) -> None:
        worker, _ = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=_response(finish_reason=finish_reason, text=text))

        with pytest.raises(LLMCompletionTruncatedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert error.stop_reason == finish_reason
        assert error.pipe_code == STOP_TEST_PIPE_CODE
        assert error.max_tokens == 4096
        assert error.output_tokens == 4096
        assert STOP_TEST_PARTIAL_TEXT not in error.message

    async def test_a_filter_value_raises_the_refusal(self, mocker: MockerFixture) -> None:
        """Mistral's own vocabulary has no refusal value, but its SDK takes any string, and the classifier reads them all."""
        worker, _ = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=_response(finish_reason=UnrecognizedStr("content_filter"), text=""))

        with pytest.raises(LLMCompletionRefusedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.stop_reason == "content_filter"

    async def test_a_normal_stop_returns_the_text_unchanged(self, mocker: MockerFixture) -> None:
        worker, _ = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=_response(finish_reason="stop", text=STOP_TEST_PARTIAL_TEXT))

        text = await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert text == STOP_TEST_PARTIAL_TEXT
