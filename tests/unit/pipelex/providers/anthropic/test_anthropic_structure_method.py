"""The request the Anthropic worker's structured call sends for each structure method, thinking aside.

``anthropic_reasoning_tools`` is the method a model that refuses a forced tool choice names, Fable 5.1 among
them, and instructor resolves it to its core tool mode, which forces one. A JSON mode defines no tool, so
nothing about the tool choice is added to its request, thinking or not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from anthropic import Omit
from anthropic.types import TextBlock

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
)
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.asyncio(loop_scope="class")
class TestAnthropicStructureMethod:
    async def test_reasoning_tools_leaves_the_tool_choice_on_auto(self, mocker: MockerFixture) -> None:
        worker, create = make_structured_worker(mocker, structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_REASONING_TOOLS)

        result = await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        request = sent_request(create)
        assert request["tool_choice"] == {"type": "auto", "disable_parallel_tool_use": True}
        assert [tool["name"] for tool in request["tools"]] == ["DummySchema"]
        # The steering line goes out beside the prompt's own system text, which it does not replace.
        assert system_texts(request) == [STEERING_LINE, PROMPT_SYSTEM_TEXT]

    async def test_tools_forces_the_response_tool(self, mocker: MockerFixture) -> None:
        worker, create = make_structured_worker(mocker, structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS)

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = sent_request(create)
        assert request["tool_choice"]["type"] == "tool"
        assert request["tool_choice"]["name"] == "DummySchema"
        assert system_texts(request) == ["You are a helpful test assistant."]

    async def test_no_thinking_effort_keeps_the_forced_tool_choice(self, mocker: MockerFixture) -> None:
        """A NONE effort turns thinking off, so the request stays the forced-choice one."""
        worker, create = make_structured_worker(
            mocker, structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS, thinking_mode=ThinkingMode.MANUAL
        )
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.NONE

        await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = sent_request(create)
        assert request["tool_choice"]["type"] == "tool"
        assert isinstance(request.get("thinking", Omit()), Omit)
        assert request["temperature"] == 0.5

    async def test_a_model_refusing_temperature_omits_it_without_thinking(self, mocker: MockerFixture) -> None:
        worker, create = make_structured_worker(mocker, structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS, accepts_temperature=False)

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert isinstance(sent_request(create).get("temperature", Omit()), Omit)

    async def test_json_mode_with_thinking_adds_no_tool_choice(self, mocker: MockerFixture) -> None:
        """A JSON mode defines no tool, so thinking adds no tool choice and no tool steering to its request."""
        worker, create = make_structured_worker(
            mocker,
            structure_method=StructureMethod.INSTRUCTOR_ANTHROPIC_JSON,
            thinking_mode=ThinkingMode.MANUAL,
            responses=[make_message(TextBlock(type="text", text='{"text": "answer"}'))],
        )
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.LOW

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        request = sent_request(create)
        assert request["thinking"] == {"type": "enabled", "budget_tokens": 1024}
        assert isinstance(request.get("tool_choice", Omit()), Omit)
        assert "tools" not in request
        assert STEERING_LINE not in system_texts(request)
