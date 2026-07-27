"""Capture-stage tests for the OpenAI Responses API token-usage path.

The Responses worker reads ``response.usage`` (input/output tokens plus cached
and reasoning detail fields) into the job's tokens_usage. Like the Chat
Completions path, this capture branch is exercised by nothing else because mock
inference never builds a worker. These tests pin the factory mapping and the
``_gen_text`` wiring with canned responses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.plugins.openai.openai_responses_factory import OpenAIResponsesFactory
from pipelex.plugins.openai.openai_responses_llm_worker import OpenAIResponsesLLMWorker
from pipelex.system.job_metadata import JobMetadata

if TYPE_CHECKING:
    from typing import Any

    from pytest_mock import MockerFixture


def _make_llm_job_with_empty_usage() -> LLMJob:
    job_metadata = JobMetadata(user_id="test-user", pipeline_run_id="test-run")
    tokens_usage = LLMTokensUsage(
        job_metadata=job_metadata,
        inference_model_name="test-model",
        inference_model_id="test-model-id",
        unit_costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 1.0},
        nb_tokens_by_category={},
    )
    return LLMJob(
        job_metadata=job_metadata,
        llm_prompt=LLMPrompt(user_text="ping"),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
        job_report=LLMJobReport(llm_tokens_usage=tokens_usage),
    )


def _make_worker(mocker: MockerFixture, response: Any) -> OpenAIResponsesLLMWorker:
    worker = object.__new__(OpenAIResponsesLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "gpt-5"
    mock_model.name = "gpt-5"
    mock_model.thinking_mode = None
    mock_model.extra_headers = None
    worker.inference_model = mock_model
    factory = OpenAIResponsesFactory(is_http_url_enabled=False)
    # make_input_items prepares prompt images / documents — not the capture path under test;
    # stub it so the test does not depend on image-prep plumbing. make_nb_tokens_by_category stays real.
    mocker.patch.object(factory, "make_input_items", new_callable=mocker.AsyncMock, return_value=[])
    worker.openai_responses_factory = factory
    client = mocker.MagicMock()
    client.responses.create = mocker.AsyncMock(return_value=response)
    worker.openai_client_for_responses = client
    return worker


class TestOpenAIResponsesUsageCapture:
    """The Responses capture branch reads provider token counts into the job's usage."""

    def test_factory_maps_basic_usage(self, mocker: MockerFixture) -> None:
        usage = mocker.MagicMock()
        usage.input_tokens = 310
        usage.output_tokens = 88
        usage.input_tokens_details = None
        usage.output_tokens_details = None

        result = OpenAIResponsesFactory(is_http_url_enabled=False).make_nb_tokens_by_category(usage=usage)

        assert result == {TokenCategory.INPUT: 310, TokenCategory.OUTPUT: 88}

    def test_factory_maps_cached_and_reasoning_details(self, mocker: MockerFixture) -> None:
        usage = mocker.MagicMock()
        usage.input_tokens = 310
        usage.output_tokens = 88
        usage.input_tokens_details = mocker.MagicMock(cached_tokens=128)
        usage.output_tokens_details = mocker.MagicMock(reasoning_tokens=55)

        result = OpenAIResponsesFactory(is_http_url_enabled=False).make_nb_tokens_by_category(usage=usage)

        assert result[TokenCategory.INPUT] == 310
        assert result[TokenCategory.OUTPUT] == 88
        assert result[TokenCategory.INPUT_CACHED] == 128
        assert result[TokenCategory.OUTPUT_REASONING] == 55

    @pytest.mark.asyncio
    async def test_worker_gen_text_captures_usage(self, mocker: MockerFixture) -> None:
        response = mocker.MagicMock()
        response.output_text = "pong"
        response.usage = mocker.MagicMock(input_tokens=310, output_tokens=88, input_tokens_details=None, output_tokens_details=None)
        worker = _make_worker(mocker, response)
        llm_job = _make_llm_job_with_empty_usage()

        text = await worker._gen_text(llm_job=llm_job)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert text == "pong"
        captured = llm_job.job_report.llm_tokens_usage
        assert captured is not None
        assert captured.nb_tokens_by_category == {TokenCategory.INPUT: 310, TokenCategory.OUTPUT: 88}

    @pytest.mark.asyncio
    async def test_worker_gen_text_no_usage_leaves_empty(self, mocker: MockerFixture) -> None:
        """Pins today's behavior: a response with no ``usage`` leaves nb_tokens_by_category empty."""
        response = mocker.MagicMock()
        response.output_text = "pong"
        response.usage = None
        worker = _make_worker(mocker, response)
        llm_job = _make_llm_job_with_empty_usage()

        await worker._gen_text(llm_job=llm_job)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        captured = llm_job.job_report.llm_tokens_usage
        assert captured is not None
        assert captured.nb_tokens_by_category == {}
