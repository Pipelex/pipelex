"""The temperature the Google LLM worker's text call sends, and the reasoning settings it says it sends.

Gemini keeps a temperature beside thinking, so one is sent unless the model lists `temperature_unsupported`,
whose provider refuses one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from google.genai import types as genai_types

from pipelex.cogt.llm import llm_worker_abstract
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from tests.helpers.google_structured_request import make_structured_worker
from tests.helpers.instructor_test_utils import make_llm_job

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.asyncio(loop_scope="class")
class TestGoogleLLMWorkerTextRequest:
    async def test_the_temperature_is_sent(self, mocker: MockerFixture) -> None:
        captured: dict[str, Any] = {}
        worker = make_structured_worker(mocker, structure_method=StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS, captured=captured)

        result = await worker._gen_text(llm_job=make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result == '{"text": "ok"}'
        config = captured["config"]
        assert isinstance(config, genai_types.GenerateContentConfig)
        assert config.temperature == 0.5

    async def test_a_model_refusing_temperature_gets_none(self, mocker: MockerFixture) -> None:
        captured: dict[str, Any] = {}
        worker = make_structured_worker(
            mocker, structure_method=StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS, captured=captured, accepts_temperature=False
        )

        await worker._gen_text(llm_job=make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert captured["config"].temperature is None

    async def test_an_adaptive_thinking_level_is_logged_as_its_wire_value(self, mocker: MockerFixture) -> None:
        """The log carries `HIGH`, the string the request sends, not the SDK's `ThinkingLevel` member."""
        captured: dict[str, Any] = {}
        worker = make_structured_worker(
            mocker, structure_method=StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS, captured=captured, thinking_mode=ThinkingMode.ADAPTIVE
        )
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH
        debug = mocker.patch.object(llm_worker_abstract.log, "debug")

        await worker._gen_text(llm_job=llm_job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert captured["config"].thinking_config == genai_types.ThinkingConfig(thinking_level=genai_types.ThinkingLevel.HIGH)
        reasoning_calls = [call for call in debug.call_args_list if call.args == ("Sending reasoning settings",)]
        assert len(reasoning_calls) == 1
        logged_fields = reasoning_calls[0].kwargs["fields"]
        assert logged_fields == {"api_name": "Google", "thinking_level": "HIGH"}
        assert type(logged_fields["thinking_level"]) is str
