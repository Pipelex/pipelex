"""The request the OpenAI chat-completions worker's structured call sends, with and without a reasoning setting.

Driven through a real instructor client over an OpenAI SDK client whose ``chat.completions.create`` records the
request and answers with a tool call, so what is asserted is what instructor actually sends. The worker
forwards a reasoning effort exactly as its text path does; whether a server accepts it beside function tools
is the server's call, as OpenAI's own chat completions refuses it on GPT-5.x while gateways serving Claude and
Gemini through this worker take it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from openai import AsyncOpenAI, Omit
from openai.types.chat import ChatCompletion, ChatCompletionMessage, ChatCompletionMessageToolCall
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_tool_call import Function

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.constraints import ListedConstraint
from pipelex.providers.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from pipelex.providers.openai.openai_config import OpenAIConfig
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from pytest_mock import MockerFixture

_OPENAI_LEVEL_MAP: dict[str, str] = {
    "none": "none",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "xhigh",
}


def _tool_call_completion() -> ChatCompletion:
    tool_call = ChatCompletionMessageToolCall(
        id="call_test",
        type="function",
        function=Function(name="DummySchema", arguments=json.dumps({"text": "answer"})),
    )
    return ChatCompletion(
        id="chatcmpl_test",
        object="chat.completion",
        created=0,
        model="test-model",
        choices=[Choice(index=0, finish_reason="tool_calls", message=ChatCompletionMessage(role="assistant", content=None, tool_calls=[tool_call]))],
    )


def _make_worker(
    mocker: MockerFixture,
    *,
    thinking_mode: ThinkingMode,
    listed_constraints: list[ListedConstraint] | None = None,
) -> tuple[OpenAICompletionsLLMWorker, AsyncMock]:
    """A worker whose instructor client is built as the worker builds it, over an SDK call that records the request."""
    from instructor import from_openai  # ruff: ignore[import-outside-top-level]

    sdk_client = AsyncOpenAI(api_key="test-key")
    create = mocker.AsyncMock(return_value=_tool_call_completion())
    mocker.patch.object(sdk_client.chat.completions, "create", new=create)

    worker = object.__new__(OpenAICompletionsLLMWorker)
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = "test-model"
    model.name = "test-model"
    model.thinking_mode = thinking_mode
    model.extra_headers = None
    model.listed_constraints = listed_constraints or []
    worker.inference_model = model
    worker.openai_completions_factory = OpenAICompletionsFactory(is_http_url_enabled=False)
    worker.instructor_for_objects = from_openai(client=sdk_client, mode=StructureMethod.INSTRUCTOR_OPENAI_TOOLS.as_instructor_mode())

    config = mocker.MagicMock()
    config.inference.llm.openai = OpenAIConfig(effort_to_level_map=_OPENAI_LEVEL_MAP)
    mocker.patch("pipelex.providers.openai.openai_completions_llm_worker.get_config", return_value=config)
    return worker, create


def _sent_request(create: AsyncMock) -> dict[str, Any]:
    create.assert_awaited_once()
    await_args = create.await_args
    assert await_args is not None
    return dict(await_args.kwargs)


def _is_omitted(request: dict[str, Any], key: str) -> bool:
    return key not in request or isinstance(request[key], Omit)


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAICompletionsStructuredRequest:
    async def test_a_reasoning_effort_reaches_the_api_and_drops_the_temperature(self, mocker: MockerFixture) -> None:
        worker, create = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.LOW

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        request = _sent_request(create)
        assert request["reasoning_effort"] == "low"
        assert _is_omitted(request, "temperature")

    async def test_without_a_reasoning_setting_the_request_is_unchanged(self, mocker: MockerFixture) -> None:
        worker, create = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = _sent_request(create)
        assert _is_omitted(request, "reasoning_effort")
        assert request["temperature"] == 0.5

    async def test_a_model_refusing_temperature_still_omits_it_without_reasoning(self, mocker: MockerFixture) -> None:
        worker, create = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, listed_constraints=[ListedConstraint.TEMPERATURE_UNSUPPORTED])

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert _is_omitted(_sent_request(create), "temperature")

    async def test_a_model_without_reasoning_refuses_it_as_its_text_path_does(self, mocker: MockerFixture) -> None:
        worker, create = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        with pytest.raises(LLMCapabilityError, match=r"does not support reasoning \(thinking_mode=none\)"):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        create.assert_not_awaited()
