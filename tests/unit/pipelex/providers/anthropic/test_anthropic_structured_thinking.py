"""The request the Anthropic worker's structured call sends with thinking on, for each tool structure method.

Thinking needs the tool choice left on auto: a manual-thinking model refuses a forced choice, and an adaptive one
accepts it and silently does not think. Driven through a real instructor client, so what is asserted is what
instructor actually sends.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from anthropic import Omit
from anthropic.types import ThinkingBlock, ToolUseBlock

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from tests.helpers.anthropic_structured_request import (
    PROMPT_SYSTEM_TEXT,
    STEERING_LINE,
    make_message,
    make_structured_worker,
    sent_request,
    system_texts,
    tool_call_message,
)
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_AUTO_TOOL_CHOICE = {"type": "auto", "disable_parallel_tool_use": True}


@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.parametrize(
    "structure_method",
    [StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS, StructureMethod.INSTRUCTOR_ANTHROPIC_REASONING_TOOLS],
)
class TestAnthropicStructuredThinking:
    async def test_manual_thinking_reaches_the_api_with_the_auto_tool_choice(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        worker, create = make_structured_worker(mocker, structure_method=structure_method, thinking_mode=ThinkingMode.MANUAL)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.LOW

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        request = sent_request(create)
        assert request["thinking"] == {"type": "enabled", "budget_tokens": 1024}
        assert request["tool_choice"] == _AUTO_TOOL_CHOICE
        assert system_texts(request) == [STEERING_LINE, PROMPT_SYSTEM_TEXT]
        assert isinstance(request.get("temperature", Omit()), Omit)

    async def test_adaptive_thinking_reaches_the_api_with_the_auto_tool_choice(
        self, mocker: MockerFixture, structure_method: StructureMethod
    ) -> None:
        worker, create = make_structured_worker(mocker, structure_method=structure_method, thinking_mode=ThinkingMode.ADAPTIVE)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = sent_request(create)
        assert request["thinking"] == {"type": "adaptive"}
        assert request["output_config"] == {"effort": "high"}
        assert request["tool_choice"] == _AUTO_TOOL_CHOICE
        assert system_texts(request) == [STEERING_LINE, PROMPT_SYSTEM_TEXT]
        assert isinstance(request.get("temperature", Omit()), Omit)

    async def test_the_budget_leaves_room_for_the_answer_under_the_timeout_cap(
        self, mocker: MockerFixture, structure_method: StructureMethod
    ) -> None:
        """The structured call caps max_tokens at 42,666 for its timeout; `max` effort's 65,536 is cut to leave a quarter of it."""
        worker, create = make_structured_worker(
            mocker, structure_method=structure_method, thinking_mode=ThinkingMode.MANUAL, default_max_tokens=128000
        )
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.MAX

        await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = sent_request(create)
        assert request["max_tokens"] == 42666
        assert request["thinking"] == {"type": "enabled", "budget_tokens": 32000}

    async def test_a_model_without_thinking_refuses_it_as_its_text_path_does(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        worker, create = make_structured_worker(mocker, structure_method=structure_method, thinking_mode=ThinkingMode.NONE)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        with pytest.raises(LLMCapabilityError, match=r"does not support reasoning \(thinking_mode=none\)"):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        create.assert_not_awaited()

    async def test_a_reask_carries_the_signed_thinking_block_back(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        """Anthropic requires the assistant turn before a tool_result to keep its thinking blocks, signature included."""
        thinking_block = ThinkingBlock(type="thinking", thinking="Let me look at the schema.", signature="sig-test")
        invalid_call = ToolUseBlock(type="tool_use", id="toolu_invalid", name="DummySchema", input={"wrong_field": "x"})
        worker, create = make_structured_worker(
            mocker,
            structure_method=structure_method,
            thinking_mode=ThinkingMode.MANUAL,
            responses=[make_message(thinking_block, invalid_call), tool_call_message()],
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
        assert reask_args.kwargs["tool_choice"] == _AUTO_TOOL_CHOICE
