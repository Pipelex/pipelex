"""The temperature the Google LLM worker's text call sends.

Gemini keeps a temperature beside thinking, so one is sent unless the model lists `temperature_unsupported`,
whose provider refuses one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from google.genai import types as genai_types

from pipelex.cogt.llm.structured_output import StructureMethod
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
