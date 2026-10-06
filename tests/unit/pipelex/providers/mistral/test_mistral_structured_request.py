"""The request the Mistral worker's structured call sends, with and without a reasoning setting.

Mistral refuses `prompt_mode="reasoning"` on every current model and takes `reasoning_effort` instead, through
instructor's tool path as on a plain call. The call is driven through a real instructor client over a Mistral SDK
client that answers with a tool call beside a thinking chunk, the shape a reasoning Mistral model returns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.exceptions import LLMCapabilityError
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from tests.helpers.instructor_test_utils import DummySchema, make_llm_job
from tests.helpers.mistral_request import is_unset, make_worker, sent_request, tool_call_response

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.mark.asyncio(loop_scope="class")
class TestMistralStructuredRequest:
    async def test_a_reasoning_effort_reaches_the_api_as_reasoning_effort(self, mocker: MockerFixture) -> None:
        worker, complete_async = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=tool_call_response())
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.MEDIUM

        result = await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result.text == "answer"
        request = sent_request(complete_async)
        assert request["reasoning_effort"] == "high"
        assert is_unset(request, "prompt_mode")
        assert request["tool_choice"] == "any"

    async def test_without_a_reasoning_setting_no_effort_is_sent(self, mocker: MockerFixture) -> None:
        worker, complete_async = make_worker(mocker, thinking_mode=ThinkingMode.MANUAL, response=tool_call_response())

        await worker._gen_object(llm_job=make_llm_job(mocker), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        request = sent_request(complete_async)
        assert is_unset(request, "reasoning_effort")
        assert request["temperature"] == 0.5

    async def test_a_model_without_reasoning_refuses_it_as_its_text_path_does(self, mocker: MockerFixture) -> None:
        worker, complete_async = make_worker(mocker, thinking_mode=ThinkingMode.NONE, response=tool_call_response())
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        with pytest.raises(LLMCapabilityError, match=r"does not support reasoning \(thinking_mode=none\)"):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        complete_async.assert_not_awaited()

    async def test_a_json_structure_method_refuses_reasoning(self, mocker: MockerFixture) -> None:
        """A reasoning reply's content is a list of chunks, which instructor's JSON parsers cannot read, so the call is refused up front."""
        worker, complete_async = make_worker(
            mocker,
            thinking_mode=ThinkingMode.MANUAL,
            response=tool_call_response(),
            structure_method=StructureMethod.INSTRUCTOR_MISTRAL_STRUCTURED_OUTPUTS,
        )
        llm_job = make_llm_job(mocker)
        llm_job.job_params.reasoning_effort = ReasoningEffort.HIGH

        with pytest.raises(LLMCapabilityError, match="instructor/mistral_tools"):
            await worker._gen_object(llm_job=llm_job, schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
        complete_async.assert_not_awaited()
