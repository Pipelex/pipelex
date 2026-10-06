"""Fakes for driving the Mistral worker's text and structured calls over a recording Mistral SDK client.

The worker's text client and its instructor client share one SDK client whose ``chat.complete_async`` records
the request and answers with a reasoning reply, a thinking chunk beside the answer, so a test asserts what is
actually sent, through instructor on the structured path.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from mistralai.client import Mistral
from mistralai.client.models import (
    AssistantMessage,
    ChatCompletionChoice,
    ChatCompletionResponse,
    FunctionCall,
    TextChunk,
    ThinkChunk,
    ToolCall,
    UsageInfo,
)
from mistralai.client.types import UNSET

from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.providers.mistral.mistral_config import MistralConfig
from pipelex.providers.mistral.mistral_factory import MistralFactory
from pipelex.providers.mistral.mistral_llm_worker import MistralLLMWorker

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from pytest_mock import MockerFixture

    from pipelex.cogt.llm.thinking_mode import ThinkingMode

MISTRAL_LEVEL_MAP: dict[str, str] = {
    "none": "disabled",
    "minimal": "reasoning",
    "low": "reasoning",
    "medium": "reasoning",
    "high": "reasoning",
    "xhigh": "reasoning",
    "max": "reasoning",
}


def _response(message: AssistantMessage) -> ChatCompletionResponse:
    return ChatCompletionResponse(
        id="cmpl_test",
        object="chat.completion",
        model="magistral-test",
        created=0,
        usage=UsageInfo(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        choices=[ChatCompletionChoice(index=0, finish_reason="tool_calls", message=message)],
    )


def tool_call_response() -> ChatCompletionResponse:
    tool_call = ToolCall(id="call_test", function=FunctionCall(name="DummySchema", arguments=json.dumps({"text": "answer"})))
    return _response(AssistantMessage(content=[ThinkChunk(thinking=[TextChunk(text="Reading the schema.")])], tool_calls=[tool_call]))


def text_response() -> ChatCompletionResponse:
    return _response(AssistantMessage(content=[ThinkChunk(thinking=[TextChunk(text="Thinking.")]), TextChunk(text="answer")]))


def make_worker(
    mocker: MockerFixture,
    *,
    thinking_mode: ThinkingMode,
    response: ChatCompletionResponse,
    structure_method: StructureMethod = StructureMethod.INSTRUCTOR_MISTRAL_TOOLS,
) -> tuple[MistralLLMWorker, AsyncMock]:
    """A worker whose text client and instructor client share one SDK client, whose call records the request."""
    from instructor import from_mistral  # ruff: ignore[import-outside-top-level]

    sdk_client = Mistral(api_key="test-key")
    complete_async = mocker.AsyncMock(return_value=response)
    mocker.patch.object(sdk_client.chat, "complete_async", new=complete_async)

    worker = object.__new__(MistralLLMWorker)
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = "magistral-test"
    model.name = "magistral-test"
    model.thinking_mode = thinking_mode
    model.structure_method = structure_method
    worker.inference_model = model
    worker.default_max_tokens = 4096
    worker.mistral_factory = MistralFactory()
    worker.mistral_client_for_text = sdk_client
    worker.instructor_for_objects = from_mistral(client=sdk_client, mode=structure_method.as_instructor_mode(), use_async=True)

    config = mocker.MagicMock()
    config.inference.llm.mistral = MistralConfig(effort_to_level_map=MISTRAL_LEVEL_MAP)
    mocker.patch("pipelex.providers.mistral.mistral_llm_worker.get_config", return_value=config)
    return worker, complete_async


def sent_request(complete_async: AsyncMock) -> dict[str, Any]:
    complete_async.assert_awaited_once()
    await_args = complete_async.await_args
    assert await_args is not None
    return dict(await_args.kwargs)


def is_unset(request: dict[str, Any], key: str) -> bool:
    return request.get(key, UNSET) is UNSET
