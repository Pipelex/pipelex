"""The temperature the OpenAI chat-completions worker's text call sends.

A temperature is sent unless a reasoning effort is, or the model lists `temperature_unsupported`, whose
provider refuses one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from tests.helpers.instructor_test_utils import make_llm_job
from tests.helpers.openai_completions_request import is_omitted, make_worker, sent_request, text_completion

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAICompletionsTextRequest:
    async def test_without_a_reasoning_setting_the_temperature_is_sent(self, mocker: MockerFixture) -> None:
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=text_completion())

        result = await worker._gen_text(llm_job=make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result == "answer"
        request = sent_request(create)
        assert request["temperature"] == 0.5
        assert is_omitted(request, "reasoning_effort")

    async def test_a_reasoning_effort_drops_the_temperature(self, mocker: MockerFixture) -> None:
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=text_completion())
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.LOW

        await worker._gen_text(llm_job=llm_job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = sent_request(create)
        assert request["reasoning_effort"] == "low"
        assert is_omitted(request, "temperature")

    async def test_a_model_refusing_temperature_omits_it_without_reasoning(self, mocker: MockerFixture) -> None:
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=text_completion(), accepts_temperature=False)

        await worker._gen_text(llm_job=make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert is_omitted(sent_request(create), "temperature")
