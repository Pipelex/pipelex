"""Fakes for driving the OpenAI chat-completions worker's text and structured calls over a recording OpenAI SDK client.

The worker's text client and its instructor client, built in tool mode as the worker builds it, share one SDK
client whose ``chat.completions.create`` records the request and answers with the completion given, so a test
asserts what is actually sent, through instructor on the structured path.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI, Omit
from openai.types.chat import ChatCompletion, ChatCompletionMessage, ChatCompletionMessageToolCall
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_tool_call import Function

from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.providers.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from pipelex.providers.openai.openai_config import OpenAIConfig

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from pytest_mock import MockerFixture

    from pipelex.cogt.llm.thinking_mode import ThinkingMode

OPENAI_LEVEL_MAP: dict[str, str] = {
    "none": "none",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "xhigh",
}


def _completion(choice: Choice) -> ChatCompletion:
    return ChatCompletion(id="chatcmpl_test", object="chat.completion", created=0, model="test-model", choices=[choice])


def tool_call_completion() -> ChatCompletion:
    tool_call = ChatCompletionMessageToolCall(
        id="call_test",
        type="function",
        function=Function(name="DummySchema", arguments=json.dumps({"text": "answer"})),
    )
    message = ChatCompletionMessage(role="assistant", content=None, tool_calls=[tool_call])
    return _completion(Choice(index=0, finish_reason="tool_calls", message=message))


def text_completion() -> ChatCompletion:
    return _completion(Choice(index=0, finish_reason="stop", message=ChatCompletionMessage(role="assistant", content="answer")))


def make_worker(
    mocker: MockerFixture,
    *,
    thinking_mode: ThinkingMode,
    response: ChatCompletion,
    accepts_temperature: bool = True,
) -> tuple[OpenAICompletionsLLMWorker, AsyncMock]:
    """A worker whose text client and instructor client share one SDK client, whose call records the request."""
    from instructor import from_openai  # ruff: ignore[import-outside-top-level]

    sdk_client = AsyncOpenAI(api_key="test-key")
    create = mocker.AsyncMock(return_value=response)
    mocker.patch.object(sdk_client.chat.completions, "create", new=create)

    worker = object.__new__(OpenAICompletionsLLMWorker)
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = "test-model"
    model.name = "test-model"
    model.thinking_mode = thinking_mode
    model.accepts_temperature = accepts_temperature
    model.extra_headers = None
    worker.inference_model = model
    worker.openai_completions_factory = OpenAICompletionsFactory(is_http_url_enabled=False)
    worker.openai_client_for_text = sdk_client
    worker.instructor_for_objects = from_openai(client=sdk_client, mode=StructureMethod.INSTRUCTOR_OPENAI_TOOLS.as_instructor_mode())

    config = mocker.MagicMock()
    config.inference.llm.openai = OpenAIConfig(effort_to_level_map=OPENAI_LEVEL_MAP)
    mocker.patch("pipelex.providers.openai.openai_completions_llm_worker.get_config", return_value=config)
    return worker, create


def sent_request(create: AsyncMock) -> dict[str, Any]:
    create.assert_awaited_once()
    await_args = create.await_args
    assert await_args is not None
    return dict(await_args.kwargs)


def is_omitted(request: dict[str, Any], key: str) -> bool:
    return key not in request or isinstance(request[key], Omit)
