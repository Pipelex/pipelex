"""Tests for the request the Google LLM worker's structured generation actually sends.

``_gen_object`` goes through ``instructor``'s genai handlers, which build the Google ``GenerateContentConfig``
themselves from the kwargs they recognise and silently drop the rest. These tests drive the real
``from_genai`` client and capture what reaches ``generate_content``, so a system prompt, temperature or token
limit lost on the way fails here rather than in production.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import pytest
from google import genai
from google.genai import types as genai_types
from instructor import from_genai
from pydantic import BaseModel

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.providers.google.google_config import GoogleConfig
from pipelex.providers.google.google_llm_worker import GoogleLLMWorker
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job

_GOOGLE_LEVEL_MAP: dict[str, str] = {
    "none": "disabled",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}
_GEMINI_BUDGET_MAP: dict[str, int] = {"none": 0, "minimal": 512, "low": 1024, "medium": 5000, "high": 16384, "xhigh": 32768, "max": 65536}


def _gemini_budget(*, family: str, effort: str) -> int:
    assert family == "gemini"
    return _GEMINI_BUDGET_MAP[effort]


class _Color(StrEnum):
    RED = "red"
    BLUE = "blue"


class _ColoredSchema(BaseModel):
    color: _Color


def _make_response(*, structure_method: StructureMethod, schema_name: str, payload: dict[str, Any]) -> genai_types.GenerateContentResponse:
    match structure_method:
        case StructureMethod.INSTRUCTOR_GENAI_TOOLS:
            part = genai_types.Part(function_call=genai_types.FunctionCall(name=schema_name, args=payload))
        case StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS:
            part = genai_types.Part(text=json.dumps(payload))
        case _:
            msg = f"No Gemini response shape for {structure_method}"
            raise ValueError(msg)
    return genai_types.GenerateContentResponse(candidates=[genai_types.Candidate(content=genai_types.Content(role="model", parts=[part]))])


def _make_worker(
    mocker: MockerFixture,
    *,
    structure_method: StructureMethod,
    captured: dict[str, Any],
    schema_name: str = DummySchema.__name__,
    payload: dict[str, Any] | None = None,
    thinking_mode: ThinkingMode | None = None,
) -> GoogleLLMWorker:
    client = genai.Client(api_key="test-key")
    response_payload = payload or {"text": "ok"}

    # The real keyword-only signature, so a keyword `generate_content` does not take fails here as it does live
    def fake_generate_content(
        *, model: str, contents: Any, config: genai_types.GenerateContentConfig | None = None
    ) -> genai_types.GenerateContentResponse:
        captured.update(model=model, contents=contents, config=config)
        return _make_response(structure_method=structure_method, schema_name=schema_name, payload=response_payload)

    mocker.patch.object(client.aio.models, "generate_content", new_callable=mocker.AsyncMock, side_effect=fake_generate_content)

    worker = object.__new__(GoogleLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "gemini-pro"
    mock_model.name = "gemini-pro"
    mock_model.thinking_mode = thinking_mode
    worker.inference_model = mock_model
    worker.instructor_for_objects = from_genai(client=client, mode=structure_method.as_instructor_mode(), use_async=True)

    config = mocker.MagicMock()
    config.inference.llm.google = GoogleConfig(effort_to_level_map=_GOOGLE_LEVEL_MAP)
    config.inference.llm.get_reasoning_budget = mocker.MagicMock(side_effect=_gemini_budget)
    mocker.patch("pipelex.providers.google.google_llm_worker.get_config", return_value=config)
    return worker


@pytest.mark.asyncio(loop_scope="class")
class TestGoogleLLMWorkerStructuredRequest:
    """``_gen_object`` must hand the prompt's system text and the job's generation controls to Google."""

    @pytest.mark.parametrize(
        "structure_method",
        [StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS, StructureMethod.INSTRUCTOR_GENAI_TOOLS],
    )
    async def test_request_config_carries_system_prompt_and_generation_controls(
        self,
        mocker: MockerFixture,
        structure_method: StructureMethod,
    ) -> None:
        captured: dict[str, Any] = {}
        worker = _make_worker(mocker, structure_method=structure_method, captured=captured)
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

    @pytest.mark.parametrize(
        "structure_method",
        [StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS, StructureMethod.INSTRUCTOR_GENAI_TOOLS],
    )
    async def test_request_without_system_text_or_token_limit_sends_none(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        """A prompt with no system text sends no system instruction, and never a `system` keyword `generate_content` refuses."""
        captured: dict[str, Any] = {}
        worker = _make_worker(mocker, structure_method=structure_method, captured=captured)
        llm_job = make_llm_job(mocker)
        llm_job.llm_prompt.system_text = None

        await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        config = captured["config"]
        assert not config.system_instruction
        assert config.temperature == 0.5
        assert config.max_output_tokens is None

    @pytest.mark.parametrize(
        "structure_method",
        [StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS, StructureMethod.INSTRUCTOR_GENAI_TOOLS],
    )
    async def test_an_enum_field_is_parsed_from_its_string_value(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        """Gemini hands an enum back as its string value, under tool calling and JSON output alike."""
        worker = _make_worker(
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


_BOTH_STRUCTURE_METHODS = [StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS, StructureMethod.INSTRUCTOR_GENAI_TOOLS]


@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.parametrize("structure_method", _BOTH_STRUCTURE_METHODS)
class TestGoogleLLMWorkerStructuredThinking:
    """A reasoning setting reaches Gemini's thinking configuration on a structured output, as it does on text."""

    async def test_a_manual_thinking_budget_reaches_the_request_config(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        captured: dict[str, Any] = {}
        worker = _make_worker(mocker, structure_method=structure_method, captured=captured, thinking_mode=ThinkingMode.MANUAL)
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
        worker = _make_worker(mocker, structure_method=structure_method, captured=captured, thinking_mode=ThinkingMode.MANUAL)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH
        llm_job.job_params.max_tokens = 4000

        await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert captured["config"].thinking_config == genai_types.ThinkingConfig(thinking_budget=3000)

    async def test_an_adaptive_thinking_level_reaches_the_request_config(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        captured: dict[str, Any] = {}
        worker = _make_worker(mocker, structure_method=structure_method, captured=captured, thinking_mode=ThinkingMode.ADAPTIVE)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert captured["config"].thinking_config == genai_types.ThinkingConfig(thinking_level=genai_types.ThinkingLevel.HIGH)

    async def test_without_a_reasoning_setting_no_thinking_config_is_sent(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        captured: dict[str, Any] = {}
        worker = _make_worker(mocker, structure_method=structure_method, captured=captured, thinking_mode=ThinkingMode.MANUAL)

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert captured["config"].thinking_config is None

    async def test_a_model_without_thinking_refuses_it_as_its_text_path_does(self, mocker: MockerFixture, structure_method: StructureMethod) -> None:
        captured: dict[str, Any] = {}
        worker = _make_worker(mocker, structure_method=structure_method, captured=captured, thinking_mode=ThinkingMode.NONE)
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        with pytest.raises(LLMCapabilityError, match=r"does not support reasoning \(thinking_mode=none\)"):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        assert not captured
