from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from openai.types import CompletionUsage
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from pipelex.cogt.exceptions import LLMCompletionRefusedError, LLMCompletionTruncatedError
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from tests.helpers.completion_stop import STOP_TEST_PARTIAL_TEXT, STOP_TEST_PIPE_CODE, make_text_llm_job
from tests.helpers.openai_completions_request import make_worker

if TYPE_CHECKING:
    from typing import Literal

    from pytest_mock import MockerFixture


def _completion(*, finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "function_call"], content: str) -> ChatCompletion:
    return ChatCompletion(
        id="chatcmpl_test",
        object="chat.completion",
        created=0,
        model="test-model",
        choices=[Choice(index=0, finish_reason=finish_reason, message=ChatCompletionMessage(role="assistant", content=content))],
        usage=CompletionUsage(prompt_tokens=50, completion_tokens=256, total_tokens=306),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAICompletionsStop:
    @pytest.mark.parametrize("content", [STOP_TEST_PARTIAL_TEXT, ""])
    async def test_a_text_cut_at_its_length_raises_the_truncation(self, mocker: MockerFixture, content: str) -> None:
        worker, _ = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=_completion(finish_reason="length", content=content))

        with pytest.raises(LLMCompletionTruncatedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job(max_tokens=256))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert error.stop_reason == "length"
        assert error.pipe_code == STOP_TEST_PIPE_CODE
        assert error.max_tokens == 256
        assert error.output_tokens == 256
        assert STOP_TEST_PARTIAL_TEXT not in error.message

    async def test_a_filtered_text_raises_the_refusal(self, mocker: MockerFixture) -> None:
        worker, _ = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=_completion(finish_reason="content_filter", content=""))

        with pytest.raises(LLMCompletionRefusedError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.stop_reason == "content_filter"
        assert exc_info.value.pipe_code == STOP_TEST_PIPE_CODE

    async def test_a_normal_stop_returns_the_text_unchanged(self, mocker: MockerFixture) -> None:
        worker, _ = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=_completion(finish_reason="stop", content=STOP_TEST_PARTIAL_TEXT))

        text = await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert text == STOP_TEST_PARTIAL_TEXT
