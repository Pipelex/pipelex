"""The requests the Mistral worker sends, on text and structured calls, with and without a reasoning setting.

Mistral refuses `prompt_mode="reasoning"` on every current model and takes `reasoning_effort` instead, on a
plain call and through instructor's tool path alike. The structured call is driven through a real instructor
client over a Mistral SDK client whose ``chat.complete_async`` records the request and answers with a tool
call beside a thinking chunk, the shape a reasoning Mistral model returns, so what is asserted is what instructor
actually sends.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
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

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.providers.mistral.mistral_config import MistralConfig
from pipelex.providers.mistral.mistral_factory import MistralFactory
from pipelex.providers.mistral.mistral_llm_worker import MistralLLMWorker
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from pytest_mock import MockerFixture

_MISTRAL_LEVEL_MAP: dict[str, str] = {
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


def _tool_call_response() -> ChatCompletionResponse:
    tool_call = ToolCall(id="call_test", function=FunctionCall(name="DummySchema", arguments=json.dumps({"text": "answer"})))
    return _response(AssistantMessage(content=[ThinkChunk(thinking=[TextChunk(text="Reading the schema.")])], tool_calls=[tool_call]))


def _text_response() -> ChatCompletionResponse:
    return _response(AssistantMessage(content=[ThinkChunk(thinking=[TextChunk(text="Thinking.")]), TextChunk(text="answer")]))


def _make_worker(mocker: MockerFixture, *, thinking_mode: ThinkingMode, response: ChatCompletionResponse) -> tuple[MistralLLMWorker, AsyncMock]:
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
    worker.inference_model = model
    worker.default_max_tokens = 4096
    worker.mistral_factory = MistralFactory()
    worker.mistral_client_for_text = sdk_client
    worker.instructor_for_objects = from_mistral(
        client=sdk_client, mode=StructureMethod.INSTRUCTOR_MISTRAL_TOOLS.as_instructor_mode(), use_async=True
    )

    config = mocker.MagicMock()
    config.inference.llm.mistral = MistralConfig(effort_to_level_map=_MISTRAL_LEVEL_MAP)
    mocker.patch("pipelex.providers.mistral.mistral_llm_worker.get_config", return_value=config)
    return worker, complete_async


def _sent_request(complete_async: AsyncMock) -> dict[str, Any]:
    complete_async.assert_awaited_once()
    await_args = complete_async.await_args
    assert await_args is not None
    return dict(await_args.kwargs)


def _is_unset(request: dict[str, Any], key: str) -> bool:
    return request.get(key, UNSET) is UNSET


@pytest.mark.asyncio(loop_scope="class")
class TestMistralStructuredRequest:
    async def test_a_reasoning_effort_reaches_the_api_as_reasoning_effort(self, mocker: MockerFixture) -> None:
        worker, complete_async = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=_tool_call_response())
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.MEDIUM

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        request = _sent_request(complete_async)
        assert request["reasoning_effort"] == "high"
        assert _is_unset(request, "prompt_mode")
        assert request["tool_choice"] == "any"

    async def test_without_a_reasoning_setting_no_effort_is_sent(self, mocker: MockerFixture) -> None:
        worker, complete_async = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=_tool_call_response())

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = _sent_request(complete_async)
        assert _is_unset(request, "reasoning_effort")
        assert request["temperature"] == 0.5

    async def test_a_model_without_reasoning_refuses_it_as_its_text_path_does(self, mocker: MockerFixture) -> None:
        worker, complete_async = _make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=_tool_call_response())
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        with pytest.raises(LLMCapabilityError, match=r"does not support reasoning \(thinking_mode=none\)"):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        complete_async.assert_not_awaited()


@pytest.mark.asyncio(loop_scope="class")
class TestMistralTextRequest:
    async def test_a_reasoning_effort_reaches_the_api_as_reasoning_effort(self, mocker: MockerFixture) -> None:
        worker, complete_async = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=_text_response())
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        result = await worker._gen_text(llm_job=llm_job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result == "answer"
        request = _sent_request(complete_async)
        assert request["reasoning_effort"] == "high"
        assert _is_unset(request, "prompt_mode")

    async def test_without_a_reasoning_setting_no_effort_is_sent(self, mocker: MockerFixture) -> None:
        worker, complete_async = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=_text_response())

        await worker._gen_text(llm_job=make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert _is_unset(_sent_request(complete_async), "reasoning_effort")
