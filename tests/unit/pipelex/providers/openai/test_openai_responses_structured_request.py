"""The request the OpenAI Responses worker's structured call sends, with and without a reasoning setting.

Driven through a real instructor client in ``RESPONSES_TOOLS`` mode over an OpenAI SDK client whose
``responses.create`` records the request and answers with a function call, so what is asserted is what
instructor actually sends. The hosted plane's ``manifold_responses`` SDK runs this worker, so a reasoning
preset on a structured pipe reaches the gateway through exactly this request.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from openai import AsyncOpenAI, Omit
from openai.types.responses import Response, ResponseFunctionToolCall

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.providers.openai.openai_config import OpenAIConfig
from pipelex.providers.openai.openai_responses_factory import OpenAIResponsesFactory
from pipelex.providers.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker
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


def _function_call_response() -> Response:
    return Response(
        id="resp_test",
        created_at=0,
        model="gpt-test",
        object="response",
        output=[ResponseFunctionToolCall(type="function_call", call_id="call_test", name="DummySchema", arguments=json.dumps({"text": "answer"}))],
        parallel_tool_calls=False,
        tool_choice="auto",
        tools=[],
    )


def _make_worker(mocker: MockerFixture, *, thinking_mode: ThinkingMode) -> tuple[OpenAIResponsesLLMWorker, AsyncMock]:
    """A worker whose instructor client is built as the worker builds it, over an SDK call that records the request."""
    from instructor import from_openai  # ruff: ignore[import-outside-top-level]

    sdk_client = AsyncOpenAI(api_key="test-key")
    create = mocker.AsyncMock(return_value=_function_call_response())
    mocker.patch.object(sdk_client.responses, "create", new=create)

    worker = object.__new__(OpenAIResponsesLLMWorker)
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = "gpt-test"
    model.name = "gpt-test"
    model.thinking_mode = thinking_mode
    model.extra_headers = None
    worker.inference_model = model
    factory = OpenAIResponsesFactory(is_http_url_enabled=False)
    mocker.patch.object(factory, "make_input_items", new_callable=mocker.AsyncMock, return_value=[{"role": "user", "content": "Generate."}])
    worker.openai_responses_factory = factory
    worker.instructor_for_objects = from_openai(client=sdk_client, mode=StructureMethod.INSTRUCTOR_OPENAI_RESPONSES_TOOLS.as_instructor_mode())

    config = mocker.MagicMock()
    config.inference.llm.openai = OpenAIConfig(effort_to_level_map=_OPENAI_LEVEL_MAP)
    mocker.patch("pipelex.providers.openai.openai_responses_llm_worker.get_config", return_value=config)
    return worker, create


def _sent_request(create: AsyncMock) -> dict[str, Any]:
    create.assert_awaited_once()
    await_args = create.await_args
    assert await_args is not None
    return dict(await_args.kwargs)


def _is_omitted(request: dict[str, Any], key: str) -> bool:
    return key not in request or isinstance(request[key], Omit)


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAIResponsesStructuredRequest:
    async def test_a_reasoning_effort_reaches_the_api_and_drops_the_temperature(self, mocker: MockerFixture) -> None:
        worker, create = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        request = _sent_request(create)
        assert request["reasoning"] == {"effort": "high"}
        assert _is_omitted(request, "temperature")
        # The structuring path itself is unchanged: the response tool is still the forced one
        assert request["tool_choice"] == {"type": "function", "name": "DummySchema"}

    async def test_without_a_reasoning_setting_the_request_is_unchanged(self, mocker: MockerFixture) -> None:
        worker, create = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = _sent_request(create)
        assert _is_omitted(request, "reasoning")
        assert request["temperature"] == 0.5

    async def test_a_model_without_reasoning_refuses_it_as_its_text_path_does(self, mocker: MockerFixture) -> None:
        worker, create = _make_worker(mocker, thinking_mode=ThinkingMode.NONE)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        with pytest.raises(LLMCapabilityError, match=r"does not support reasoning \(thinking_mode=none\)"):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        create.assert_not_awaited()

    async def test_a_reasoning_budget_is_refused_as_its_text_path_does(self, mocker: MockerFixture) -> None:
        worker, create = _make_worker(mocker, thinking_mode=ThinkingMode.MANUAL)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_budget = 4096

        with pytest.raises(LLMCapabilityError, match="does not support reasoning_budget; OpenAI uses reasoning_effort instead"):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        create.assert_not_awaited()
