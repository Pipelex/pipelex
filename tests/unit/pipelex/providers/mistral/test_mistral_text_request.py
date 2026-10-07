"""The request the Mistral worker's text call sends, with and without a reasoning setting.

Mistral refuses `prompt_mode="reasoning"` on every current model and takes `reasoning_effort` instead. It takes a
temperature beside it, so one is sent unless the model lists `temperature_unsupported`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from tests.helpers.instructor_test_utils import make_llm_job
from tests.helpers.mistral_request import is_unset, make_worker, sent_request, text_response

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.asyncio(loop_scope="class")
class TestMistralTextRequest:
    async def test_a_reasoning_effort_reaches_the_api_as_reasoning_effort(self, mocker: MockerFixture) -> None:
        worker, complete_async = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=text_response())
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        result = await worker._gen_text(llm_job=llm_job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result == "answer"
        request = sent_request(complete_async)
        assert request["reasoning_effort"] == "high"
        assert is_unset(request, "prompt_mode")

    async def test_without_a_reasoning_setting_no_effort_is_sent(self, mocker: MockerFixture) -> None:
        worker, complete_async = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=text_response())

        await worker._gen_text(llm_job=make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = sent_request(complete_async)
        assert is_unset(request, "reasoning_effort")
        assert request["temperature"] == 0.5

    async def test_a_model_refusing_temperature_omits_it(self, mocker: MockerFixture) -> None:
        worker, complete_async = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=text_response(), accepts_temperature=False)

        await worker._gen_text(llm_job=make_llm_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert is_unset(sent_request(complete_async), "temperature")
