"""The request the OpenAI Responses worker's structured call sends, with and without a reasoning setting.

Driven through a real instructor client in ``RESPONSES_TOOLS`` mode over an OpenAI SDK client whose
``responses.create`` records the request and answers with a function call, so what is asserted is what
instructor actually sends. The hosted plane's ``manifold_responses`` SDK runs this worker, so a reasoning
preset on a structured pipe reaches the gateway through exactly this request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job
from tests.helpers.openai_responses_request import function_call_response, is_omitted, make_worker, sent_request

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAIResponsesStructuredRequest:
    async def test_a_reasoning_effort_reaches_the_api_and_drops_the_temperature(self, mocker: MockerFixture) -> None:
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=function_call_response())
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        request = sent_request(create)
        assert request["reasoning"] == {"effort": "high"}
        assert is_omitted(request, "temperature")
        # The structuring path itself is unchanged: the response tool is still the forced one
        assert request["tool_choice"] == {"type": "function", "name": "DummySchema"}

    async def test_without_a_reasoning_setting_the_request_is_unchanged(self, mocker: MockerFixture) -> None:
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=function_call_response())

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = sent_request(create)
        assert is_omitted(request, "reasoning")
        assert request["temperature"] == 0.5

    async def test_a_model_refusing_temperature_omits_it_without_reasoning(self, mocker: MockerFixture) -> None:
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=function_call_response(), accepts_temperature=False)

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert is_omitted(sent_request(create), "temperature")

    async def test_a_model_without_reasoning_refuses_it_as_its_text_path_does(self, mocker: MockerFixture) -> None:
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=function_call_response())
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        with pytest.raises(LLMCapabilityError, match=r"does not support reasoning \(thinking_mode=none\)"):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        create.assert_not_awaited()

    async def test_a_reasoning_budget_is_refused_as_its_text_path_does(self, mocker: MockerFixture) -> None:
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=function_call_response())
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_budget = 4096

        with pytest.raises(LLMCapabilityError, match="does not support reasoning_budget; OpenAI uses reasoning_effort instead"):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        create.assert_not_awaited()
