"""Tests for the request the Google LLM worker's structured generation actually sends.

``_gen_object`` goes through ``instructor``'s genai handlers, which build the Google ``GenerateContentConfig``
themselves from the kwargs they recognise and silently drop the rest. These tests drive the real
``from_genai`` client and capture what reaches ``generate_content``, so a system prompt, temperature or token
limit lost on the way fails here rather than in production.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

import pytest
from google.genai import types as genai_types
from pydantic import BaseModel

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.llm.structured_output import StructureMethod

from tests.helpers.google_structured_request import GENAI_STRUCTURE_METHODS, make_structured_worker
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job


class _Color(StrEnum):
    RED = "red"
    BLUE = "blue"


class _ColoredSchema(BaseModel):
    color: _Color


@pytest.mark.asyncio(loop_scope="class")
class TestGoogleLLMWorkerStructuredRequest:
    """``_gen_object`` must hand the prompt's system text and the job's generation controls to Google."""

    @pytest.mark.parametrize("structure_method", GENAI_STRUCTURE_METHODS)
    async def test_request_config_carries_system_prompt_and_generation_controls(
        self,
        mocker: MockerFixture,
        structure_method: StructureMethod,
    ) -> None:
        captured: dict[str, Any] = {}
        worker = make_structured_worker(mocker, structure_method=structure_method, captured=captured)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.temperature = 0.3
        llm_job.job_params.max_tokens = 123

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "ok"
        config = captured["config"]
        assert isinstance(config, genai_types.GenerateContentConfig)
        assert config.system_instruction == llm_job.llm_prompt.system_text
        assert config.temperature == 0.3
        assert config.max_output_tokens == 123
        assert config.candidate_count == 1

    @pytest.mark.parametrize("structure_method", GENAI_STRUCTURE_METHODS)
    async def test_request_without_system_text_or_token_limit_sends_none(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        """A prompt with no system text sends no system instruction, and never a `system` keyword `generate_content` refuses."""
        captured: dict[str, Any] = {}
        worker = make_structured_worker(mocker, structure_method=structure_method, captured=captured)
        llm_job = make_llm_job(mocker)
        llm_job.llm_prompt.system_text = None

        await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        config = captured["config"]
        assert not config.system_instruction
        assert config.temperature == 0.5
        assert config.max_output_tokens is None

    @pytest.mark.parametrize("structure_method", GENAI_STRUCTURE_METHODS)
    async def test_a_model_refusing_temperature_gets_none(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        captured: dict[str, Any] = {}
        worker = make_structured_worker(mocker, structure_method=structure_method, captured=captured, accepts_temperature=False)

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert captured["config"].temperature is None

    @pytest.mark.parametrize("structure_method", GENAI_STRUCTURE_METHODS)
    async def test_an_enum_field_is_parsed_from_its_string_value(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        """Gemini hands an enum back as its string value, under tool calling and JSON output alike."""
        worker = make_structured_worker(
            mocker,
            structure_method=structure_method,
            captured={},
            schema_name=_ColoredSchema.__name__,
            payload={"color": "red"},
        )
        llm_job = make_llm_job(mocker)
        llm_job.job_config.schema_reask_max_attempts = 1

        result = await worker._gen_object(llm_job=llm_job, schema=_ColoredSchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.color is _Color.RED
