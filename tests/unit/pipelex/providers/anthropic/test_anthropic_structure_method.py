"""The request the Anthropic worker's structured call sends, for each tool structure method, with and without thinking.

Driven through a real instructor client over an Anthropic SDK client whose ``messages.create`` records the
request and answers with a tool call, so what is asserted is what instructor actually sends, not the arguments
the worker hands it. ``anthropic_reasoning_tools`` is the method a model that refuses a forced tool choice
names, Fable 5.1 among them, and instructor resolves it to its core tool mode, which forces one. Thinking needs
the tool choice left on auto too: a manual-thinking model refuses a forced choice, and an adaptive one accepts
it and silently does not think.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from anthropic import AsyncAnthropic, Omit
from anthropic.types import ContentBlock, Message, ThinkingBlock, ToolUseBlock, Usage

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.providers.anthropic.anthropic_config import AnthropicConfig
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from pytest_mock import MockerFixture


_ANTHROPIC_LEVEL_MAP: dict[str, str] = {
    "none": "disabled",
    "minimal": "low",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "max",
}
_ANTHROPIC_BUDGET_MAP: dict[str, int] = {"none": 0, "minimal": 512, "low": 1024, "medium": 5000, "high": 16384, "xhigh": 32768, "max": 65536}


def _anthropic_budget(*, family: str, effort: str) -> int:
    assert family == "anthropic"
    return _ANTHROPIC_BUDGET_MAP[effort]


_STEERING_LINE = "Return only the tool call and no additional text."
_PROMPT_SYSTEM_TEXT = "You are a helpful test assistant."


def _message(*content: ContentBlock) -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-test",
        content=list(content),
        stop_reason="tool_use",
        stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


def _tool_call_message() -> Message:
    return _message(ToolUseBlock(type="tool_use", id="toolu_test", name="DummySchema", input={"text": "answer"}))


def _make_worker(
    mocker: MockerFixture,
    *,
    structure_method: StructureMethod,
    thinking_mode: ThinkingMode = ThinkingMode.NONE,
    default_max_tokens: int = 4096,
    responses: list[Message] | None = None,
) -> tuple[AnthropicLLMWorker, AsyncMock]:
    """A worker whose instructor client is built as the worker builds it, over an SDK call that records the request."""
    from instructor import from_anthropic  # ruff: ignore[import-outside-top-level]

    sdk_client = AsyncAnthropic(api_key="test-key")
    if responses is None:
        create = mocker.AsyncMock(return_value=_tool_call_message())
    else:
        create = mocker.AsyncMock(side_effect=responses)
    mocker.patch.object(sdk_client.messages, "create", new=create)

    worker = object.__new__(AnthropicLLMWorker)

    worker.extras_factory = None
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = "claude-test"
    model.name = "claude-test"
    model.listed_constraints = []
    model.structure_method = structure_method
    model.thinking_mode = thinking_mode
    worker.inference_model = model
    worker.default_max_tokens = default_max_tokens
    worker.instructor_for_objects = from_anthropic(client=sdk_client, mode=structure_method.as_instructor_mode())

    config = mocker.MagicMock()
    config.inference.llm.anthropic = AnthropicConfig(structured_output_timeout_seconds=1200, effort_to_level_map=_ANTHROPIC_LEVEL_MAP)
    config.inference.llm.get_reasoning_budget = mocker.MagicMock(side_effect=_anthropic_budget)
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

    async def test_no_thinking_effort_keeps_the_forced_tool_choice(self, mocker: MockerFixture) -> None:
        """A NONE effort turns thinking off, so the request stays the forced-choice one."""
        worker, create = _make_worker(mocker, structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS, thinking_mode=ThinkingMode.MANUAL)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.NONE

        await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = _sent_request(create)
        assert request["tool_choice"]["type"] == "tool"
        assert isinstance(request.get("thinking", Omit()), Omit)
        assert request["temperature"] == 0.5


@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.parametrize(
    "structure_method",
    [StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS, StructureMethod.INSTRUCTOR_ANTHROPIC_REASONING_TOOLS],
)
class TestAnthropicStructuredThinking:
    async def test_manual_thinking_reaches_the_api_with_the_auto_tool_choice(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        worker, create = _make_worker(mocker, structure_method=structure_method, thinking_mode=ThinkingMode.MANUAL)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.LOW

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        request = _sent_request(create)
        assert request["thinking"] == {"type": "enabled", "budget_tokens": 1024}
        assert request["tool_choice"] == {"type": "auto"}
        assert _system_texts(request) == [_STEERING_LINE, _PROMPT_SYSTEM_TEXT]
        assert isinstance(request.get("temperature", Omit()), Omit)

    async def test_adaptive_thinking_reaches_the_api_with_the_auto_tool_choice(
        self, mocker: MockerFixture, structure_method: StructureMethod
    ) -> None:
        worker, create = _make_worker(mocker, structure_method=structure_method, thinking_mode=ThinkingMode.ADAPTIVE)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = _sent_request(create)
        assert request["thinking"] == {"type": "adaptive"}
        assert request["output_config"] == {"effort": "high"}
        assert request["tool_choice"] == {"type": "auto"}
        assert _system_texts(request) == [_STEERING_LINE, _PROMPT_SYSTEM_TEXT]
        assert isinstance(request.get("temperature", Omit()), Omit)

    async def test_the_budget_leaves_room_for_the_answer_under_the_timeout_cap(
        self, mocker: MockerFixture, structure_method: StructureMethod
    ) -> None:
        """The structured call caps max_tokens at 42,666 for its timeout; `max` effort's 65,536 is cut to leave a quarter of it."""
        worker, create = _make_worker(mocker, structure_method=structure_method, thinking_mode=ThinkingMode.MANUAL, default_max_tokens=128000)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.MAX

        await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = _sent_request(create)
        assert request["max_tokens"] == 42666
        assert request["thinking"] == {"type": "enabled", "budget_tokens": 32000}

    async def test_a_model_without_thinking_refuses_it_as_its_text_path_does(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        worker, create = _make_worker(mocker, structure_method=structure_method, thinking_mode=ThinkingMode.NONE)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        with pytest.raises(LLMCapabilityError, match=r"does not support reasoning \(thinking_mode=none\)"):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        create.assert_not_awaited()

    async def test_a_reask_carries_the_signed_thinking_block_back(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        """Anthropic requires the assistant turn before a tool_result to keep its thinking blocks, signature included."""
        thinking_block = ThinkingBlock(type="thinking", thinking="Let me look at the schema.", signature="sig-test")
        invalid_call = ToolUseBlock(type="tool_use", id="toolu_invalid", name="DummySchema", input={"wrong_field": "x"})
        worker, create = _make_worker(
            mocker,
            structure_method=structure_method,
            thinking_mode=ThinkingMode.MANUAL,
            responses=[_message(thinking_block, invalid_call), _tool_call_message()],
        )
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.LOW
        llm_job.job_config.schema_reask_max_attempts = 2

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        assert create.await_count == 2
        reask_args = create.await_args_list[1]
        reask_messages = reask_args.kwargs["messages"]
        assistant_turn = reask_messages[-2]
        assert assistant_turn["role"] == "assistant"
        assert assistant_turn["content"][0] == {"type": "thinking", "thinking": "Let me look at the schema.", "signature": "sig-test"}
        assert assistant_turn["content"][1]["type"] == "tool_use"
        tool_result_turn = reask_messages[-1]
        assert tool_result_turn["content"][0]["type"] == "tool_result"
        assert tool_result_turn["content"][0]["tool_use_id"] == "toolu_invalid"
        # The re-ask keeps thinking on and the tool choice on auto
        assert reask_args.kwargs["thinking"] == {"type": "enabled", "budget_tokens": 1024}
        assert reask_args.kwargs["tool_choice"] == {"type": "auto"}
