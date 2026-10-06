"""Fakes for driving the OpenAI Responses worker's text and structured calls over a recording OpenAI SDK client.

The worker's text client and its instructor client, built in ``RESPONSES_TOOLS`` mode as the worker builds it,
share one SDK client whose ``responses.create`` records the request and answers with the response given, so a
test asserts what is actually sent, through instructor on the structured path. The hosted plane's
``manifold_responses`` SDK runs this worker, so this is the request that reaches the gateway.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI, Omit
from openai.types.responses import Response, ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.providers.openai.openai_config import OpenAIConfig
from pipelex.providers.openai.openai_responses_factory import OpenAIResponsesFactory
from pipelex.providers.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from openai.types.responses import ResponseOutputItem
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


def _response(output: list[ResponseOutputItem]) -> Response:
    return Response(
        id="resp_test",
        created_at=0,
        model="gpt-test",
        object="response",
        output=output,
        parallel_tool_calls=False,
        tool_choice="auto",
        tools=[],
    )


def function_call_response() -> Response:
    return _response(
        [ResponseFunctionToolCall(type="function_call", call_id="call_test", name="DummySchema", arguments=json.dumps({"text": "answer"}))]
    )


def text_response() -> Response:
    message = ResponseOutputMessage(
        id="msg_test",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text="answer", annotations=[])],
    )
    return _response([message])


def make_worker(
    mocker: MockerFixture,
    *,
    thinking_mode: ThinkingMode,
    response: Response,
    accepts_temperature: bool = True,
) -> tuple[OpenAIResponsesLLMWorker, AsyncMock]:
    """A worker whose text client and instructor client share one SDK client, whose call records the request."""
    from instructor import from_openai  # ruff: ignore[import-outside-top-level]

    sdk_client = AsyncOpenAI(api_key="test-key")
    create = mocker.AsyncMock(return_value=response)
    mocker.patch.object(sdk_client.responses, "create", new=create)

    worker = object.__new__(OpenAIResponsesLLMWorker)
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = "gpt-test"
    model.name = "gpt-test"
    model.thinking_mode = thinking_mode
    model.accepts_temperature = accepts_temperature
    model.extra_headers = None
    worker.inference_model = model
    factory = OpenAIResponsesFactory(is_http_url_enabled=False)
    mocker.patch.object(factory, "make_input_items", new_callable=mocker.AsyncMock, return_value=[{"role": "user", "content": "Generate."}])
    worker.openai_responses_factory = factory
    worker.openai_client_for_responses = sdk_client
    worker.instructor_for_objects = from_openai(client=sdk_client, mode=StructureMethod.INSTRUCTOR_OPENAI_RESPONSES_TOOLS.as_instructor_mode())

    config = mocker.MagicMock()
    config.inference.llm.openai = OpenAIConfig(effort_to_level_map=OPENAI_LEVEL_MAP)
    mocker.patch("pipelex.providers.openai.openai_responses_llm_worker.get_config", return_value=config)
    return worker, create


def sent_request(create: AsyncMock) -> dict[str, Any]:
    create.assert_awaited_once()
    await_args = create.await_args
    assert await_args is not None
    return dict(await_args.kwargs)


def is_omitted(request: dict[str, Any], key: str) -> bool:
    return key not in request or isinstance(request[key], Omit)
