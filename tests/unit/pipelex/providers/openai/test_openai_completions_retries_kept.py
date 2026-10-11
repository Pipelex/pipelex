from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import openai
import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage, ChatCompletionMessageToolCall
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_tool_call import Function

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from tests.helpers.completion_stop import make_text_llm_job
from tests.helpers.instructor_test_utils import DummySchema
from tests.helpers.openai_completions_request import make_worker, text_completion, tool_call_completion

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _invalid_tool_call_completion() -> ChatCompletion:
    """A tool call whose arguments miss the schema's required field, so validation fails and instructor re-asks."""
    tool_call = ChatCompletionMessageToolCall(
        id="call_invalid",
        type="function",
        function=Function(name="DummySchema", arguments=json.dumps({"wrong_field": "answer"})),
    )
    message = ChatCompletionMessage(role="assistant", content=None, tool_calls=[tool_call])
    return ChatCompletion(
        id="chatcmpl_invalid",
        object="chat.completion",
        created=0,
        model="test-model",
        choices=[Choice(index=0, finish_reason="tool_calls", message=message)],
    )


def _rate_limit_error() -> openai.RateLimitError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return openai.RateLimitError("Rate limit exceeded", response=httpx.Response(429, request=request), body=None)


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAICompletionsRetriesKept:
    async def test_a_structured_output_failing_validation_is_retried_as_configured(self, mocker: MockerFixture) -> None:
        """The stop check reads text generation only: a structured attempt that fails validation is re-asked, up to the configured count."""
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=tool_call_completion())
        create.side_effect = [_invalid_tool_call_completion(), tool_call_completion()]
        llm_job = make_text_llm_job()
        llm_job.job_config.schema_reask_max_attempts = 2

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        assert create.await_count == 2

    async def test_the_configured_count_bounds_the_retries(self, mocker: MockerFixture) -> None:
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=tool_call_completion())
        create.side_effect = [_invalid_tool_call_completion() for _ in range(5)]
        llm_job = make_text_llm_job()
        llm_job.job_config.schema_reask_max_attempts = 3

        with pytest.raises(LLMCompletionError):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert create.await_count == 3

    async def test_a_rate_limited_text_call_stays_retryable(self, mocker: MockerFixture) -> None:
        """A provider failure on the text path is classified as before, its retryable category untouched by the stop check."""
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=text_completion())
        create.side_effect = _rate_limit_error()

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker._gen_text(llm_job=make_text_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category == InferenceErrorCategory.TRANSIENT
        assert exc_info.value.to_error_report().retryable is True
