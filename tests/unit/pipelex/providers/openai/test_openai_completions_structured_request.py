"""The request the OpenAI chat-completions worker's structured call sends, with and without a reasoning setting.

Driven through a real instructor client over an OpenAI SDK client whose ``chat.completions.create`` records the
request and answers with a tool call, so what is asserted is what instructor actually sends. The worker
forwards a reasoning effort exactly as its text path does; whether a server accepts it beside function tools
is the server's call, as OpenAI's own chat completions refuses it on GPT-5.x while gateways serving Claude and
Gemini through this worker take it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job
from tests.helpers.openai_completions_request import is_omitted, make_worker, sent_request, tool_call_completion

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.asyncio(loop_scope="class")
class TestOpenAICompletionsStructuredRequest:
    async def test_a_reasoning_effort_reaches_the_api_and_drops_the_temperature(self, mocker: MockerFixture) -> None:
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=tool_call_completion())
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.LOW

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        request = sent_request(create)
        assert request["reasoning_effort"] == "low"
        assert is_omitted(request, "temperature")

    async def test_without_a_reasoning_setting_the_request_is_unchanged(self, mocker: MockerFixture) -> None:
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=tool_call_completion())

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = sent_request(create)
        assert is_omitted(request, "reasoning_effort")
        assert request["temperature"] == 0.5

    async def test_a_model_refusing_temperature_still_omits_it_without_reasoning(self, mocker: MockerFixture) -> None:
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=tool_call_completion(), accepts_temperature=False)

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert is_omitted(sent_request(create), "temperature")

    async def test_a_model_without_reasoning_refuses_it_as_its_text_path_does(self, mocker: MockerFixture) -> None:
        worker, create = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=tool_call_completion())
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        with pytest.raises(LLMCapabilityError, match=r"does not support reasoning \(thinking_mode=none\)"):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        create.assert_not_awaited()
