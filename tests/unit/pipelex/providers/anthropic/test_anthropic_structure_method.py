"""The request the Anthropic worker's structured call sends, for each tool structure method.

Driven through a real instructor client over an Anthropic SDK client whose ``messages.create`` records the
request and answers with a tool call, so what is asserted is what instructor actually sends, not the arguments
the worker hands it. ``anthropic_reasoning_tools`` is the method a model that refuses a forced tool choice
names, Fable 5.1 among them, and instructor resolves it to its core tool mode, which forces one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from anthropic import AsyncAnthropic
from anthropic.types import Message, ToolUseBlock, Usage

from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from pytest_mock import MockerFixture


def _tool_call_message() -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-test",
        content=[ToolUseBlock(type="tool_use", id="toolu_test", name="DummySchema", input={"text": "answer"})],
        stop_reason="tool_use",
        stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


def _make_worker(mocker: MockerFixture, *, structure_method: StructureMethod) -> tuple[AnthropicLLMWorker, AsyncMock]:
    """A worker whose instructor client is built as the worker builds it, over an SDK call that records the request."""
    from instructor import from_anthropic  # ruff: ignore[import-outside-top-level]

    sdk_client = AsyncAnthropic(api_key="test-key")
    create = mocker.AsyncMock(return_value=_tool_call_message())
    mocker.patch.object(sdk_client.messages, "create", new=create)

    worker = object.__new__(AnthropicLLMWorker)

    worker.extras_factory = None
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = "claude-test"
    model.name = "claude-test"
    model.listed_constraints = []
    model.structure_method = structure_method
    worker.inference_model = model
    worker.default_max_tokens = 4096
    worker.instructor_for_objects = from_anthropic(client=sdk_client, mode=structure_method.as_instructor_mode())

    config = mocker.MagicMock()
    config.inference.llm.anthropic.structured_output_timeout_seconds = 1200
    mocker.patch("pipelex.providers.anthropic.anthropic_llm_worker.get_config", return_value=config)
    return worker, create


def _sent_request(create: AsyncMock) -> dict[str, Any]:
    create.assert_awaited_once()
    await_args = create.await_args
    assert await_args is not None
    return dict(await_args.kwargs)


def _system_texts(request: dict[str, Any]) -> list[str]:
    system = request["system"]
    if isinstance(system, str):
        return [system]
    return [block["text"] for block in system]


@pytest.mark.asyncio(loop_scope="class")
class TestAnthropicStructureMethod:
    async def test_reasoning_tools_leaves_the_tool_choice_on_auto(self, mocker: MockerFixture) -> None:
        worker, create = _make_worker(mocker, structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_REASONING_TOOLS)

        result = await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        request = _sent_request(create)
        assert request["tool_choice"] == {"type": "auto"}
        assert [tool["name"] for tool in request["tools"]] == ["DummySchema"]
        # The steering line goes out beside the prompt's own system text, which it does not replace.
        assert _system_texts(request) == ["Return only the tool call and no additional text.", "You are a helpful test assistant."]

    async def test_tools_forces_the_response_tool(self, mocker: MockerFixture) -> None:
        worker, create = _make_worker(mocker, structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS)

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = _sent_request(create)
        assert request["tool_choice"]["type"] == "tool"
        assert request["tool_choice"]["name"] == "DummySchema"
        assert _system_texts(request) == ["You are a helpful test assistant."]
