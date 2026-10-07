"""A reasoning setting reaches Gemini's thinking configuration on a structured output, as it does on text.

Driven through a real ``from_genai`` client whose ``generate_content`` captures the request config.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from google.genai import types as genai_types

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.llm.structured_output import StructureMethod

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from tests.helpers.google_structured_request import GENAI_STRUCTURE_METHODS, make_structured_worker
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job


@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.parametrize("structure_method", GENAI_STRUCTURE_METHODS)
class TestGoogleLLMWorkerStructuredThinking:
    async def test_a_manual_thinking_budget_reaches_the_request_config(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        captured: dict[str, Any] = {}
        worker = make_structured_worker(mocker, structure_method=structure_method, captured=captured, thinking_mode=ThinkingMode.MANUAL)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.LOW

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "ok"
        config = captured["config"]
        assert config.thinking_config == genai_types.ThinkingConfig(thinking_budget=1024)
        # Gemini keeps the temperature beside thinking, as the text path does
        assert config.temperature == 0.5

    async def test_the_budget_is_fitted_inside_max_tokens(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        captured: dict[str, Any] = {}
        worker = make_structured_worker(mocker, structure_method=structure_method, captured=captured, thinking_mode=ThinkingMode.MANUAL)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH
        llm_job.job_params.max_tokens = 4000

        await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert captured["config"].thinking_config == genai_types.ThinkingConfig(thinking_budget=3000)

    async def test_the_budget_is_held_to_the_model_maximum_without_max_tokens(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        """`max` effort's 65,536 is beyond gemini-2.5-pro's 32,768, and no max_tokens is set to fit it in."""
        captured: dict[str, Any] = {}
        worker = make_structured_worker(
            mocker,
            structure_method=structure_method,
            captured=captured,
            thinking_mode=ThinkingMode.MANUAL,
            min_thinking_budget=128,
            max_thinking_budget=32768,
        )
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.MAX

        await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert captured["config"].max_output_tokens is None
        assert captured["config"].thinking_config == genai_types.ThinkingConfig(thinking_budget=32768)

    async def test_an_adaptive_thinking_level_reaches_the_request_config(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        captured: dict[str, Any] = {}
        worker = make_structured_worker(mocker, structure_method=structure_method, captured=captured, thinking_mode=ThinkingMode.ADAPTIVE)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert captured["config"].thinking_config == genai_types.ThinkingConfig(thinking_level=genai_types.ThinkingLevel.HIGH)

    async def test_without_a_reasoning_setting_no_thinking_config_is_sent(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        captured: dict[str, Any] = {}
        worker = make_structured_worker(mocker, structure_method=structure_method, captured=captured, thinking_mode=ThinkingMode.MANUAL)

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert captured["config"].thinking_config is None

    async def test_a_model_without_thinking_refuses_it_as_its_text_path_does(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        captured: dict[str, Any] = {}
        worker = make_structured_worker(mocker, structure_method=structure_method, captured=captured, thinking_mode=ThinkingMode.NONE)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        with pytest.raises(LLMCapabilityError, match=r"does not support reasoning \(thinking_mode=none\)"):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert not captured
