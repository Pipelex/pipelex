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

from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.providers.google.google_llm_worker import GoogleLLMWorker
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job


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
) -> GoogleLLMWorker:
    client = genai.Client(api_key="test-key")
    response_payload = payload or {"text": "ok"}

    def fake_generate_content(**kwargs: Any) -> genai_types.GenerateContentResponse:
        captured.update(kwargs)
        return _make_response(structure_method=structure_method, schema_name=schema_name, payload=response_payload)

    mocker.patch.object(client.aio.models, "generate_content", new_callable=mocker.AsyncMock, side_effect=fake_generate_content)

    worker = object.__new__(GoogleLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "gemini-pro"
    mock_model.name = "gemini-pro"
    mock_model.thinking_mode = None
    worker.inference_model = mock_model
    worker.instructor_for_objects = from_genai(client=client, mode=structure_method.as_instructor_mode(), use_async=True)
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

    async def test_request_without_system_text_or_token_limit_sends_none(self, mocker: MockerFixture) -> None:
        captured: dict[str, Any] = {}
        worker = _make_worker(mocker, structure_method=StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS, captured=captured)
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
