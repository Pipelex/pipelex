"""Capture-stage tests for the OpenAI Chat Completions token-usage path.

Cost reporting starts by reading the provider response's token counts into
``LLMJob.job_report.llm_tokens_usage.nb_tokens_by_category``. Mock inference
short-circuits before a worker is ever built, so this branch — the
``(usage := response.usage)`` read inside ``_gen_text`` and the factory mapping
it delegates to — is asserted by nothing else. These tests feed canned provider
responses through the real factory and worker to pin it.
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
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.plugins.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker

if TYPE_CHECKING:
    from typing import Any

    from pytest_mock import MockerFixture


def _make_llm_job_with_empty_usage() -> LLMJob:
    """Build an LLMJob whose tokens_usage is seeded empty, mirroring ``llm_job_before_start``."""
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


def _make_worker(mocker: MockerFixture, response: Any) -> OpenAICompletionsLLMWorker:
    """An OpenAICompletionsLLMWorker with the real factory and a canned-response client."""
    worker = object.__new__(OpenAICompletionsLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "gpt-4o"
    mock_model.name = "gpt-4o"
    mock_model.thinking_mode = None
    mock_model.listed_constraints = []
    mock_model.extra_headers = None
    worker.inference_model = mock_model
    worker.openai_completions_factory = OpenAICompletionsFactory(is_http_url_enabled=False)
    client = mocker.MagicMock()
    client.chat.completions.create = mocker.AsyncMock(return_value=response)
    worker.openai_client_for_text = client
    return worker


def _make_text_response(mocker: MockerFixture, usage: Any, content: str = "pong") -> Any:
    response = mocker.MagicMock()
    choice = mocker.MagicMock(finish_reason="stop")
    choice.message.content = content
    response.choices = [choice]
    response.usage = usage
    return response


class TestOpenAICompletionsUsageCapture:
    """The Chat Completions capture branch reads provider token counts into the job's usage."""

    def test_factory_maps_basic_usage(self, mocker: MockerFixture) -> None:
        """``make_nb_tokens_by_category`` maps prompt/completion tokens to INPUT/OUTPUT."""
        usage = mocker.MagicMock()
        usage.prompt_tokens = 120
        usage.completion_tokens = 47
        usage.prompt_tokens_details = None
        usage.completion_tokens_details = None

        result = OpenAICompletionsFactory(is_http_url_enabled=False).make_nb_tokens_by_category(usage=usage)

        assert result == {TokenCategory.INPUT: 120, TokenCategory.OUTPUT: 47}

    def test_factory_maps_cached_audio_and_reasoning_details(self, mocker: MockerFixture) -> None:
        """Cached/audio/reasoning/prediction detail fields map to their own token categories."""
        usage = mocker.MagicMock()
        usage.prompt_tokens = 200
        usage.completion_tokens = 90
        usage.prompt_tokens_details = mocker.MagicMock(audio_tokens=5, cached_tokens=64)
        usage.completion_tokens_details = mocker.MagicMock(
            audio_tokens=3,
            reasoning_tokens=40,
            accepted_prediction_tokens=2,
            rejected_prediction_tokens=1,
        )

        result = OpenAICompletionsFactory(is_http_url_enabled=False).make_nb_tokens_by_category(usage=usage)

        assert result[TokenCategory.INPUT] == 200
        assert result[TokenCategory.OUTPUT] == 90
        assert result[TokenCategory.INPUT_AUDIO] == 5
        assert result[TokenCategory.INPUT_CACHED] == 64
        assert result[TokenCategory.OUTPUT_AUDIO] == 3
        assert result[TokenCategory.OUTPUT_REASONING] == 40
        assert result[TokenCategory.OUTPUT_ACCEPTED_PREDICTION] == 2
        assert result[TokenCategory.OUTPUT_REJECTED_PREDICTION] == 1

    @pytest.mark.asyncio
    async def test_worker_gen_text_captures_usage(self, mocker: MockerFixture) -> None:
        """``_gen_text`` reads ``response.usage`` and populates the job's tokens_usage."""
        usage = mocker.MagicMock(prompt_tokens=120, completion_tokens=47, prompt_tokens_details=None, completion_tokens_details=None)
        worker = _make_worker(mocker, _make_text_response(mocker, usage=usage))
        llm_job = _make_llm_job_with_empty_usage()

        text = await worker._gen_text(llm_job=llm_job)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert text == "pong"
        captured = llm_job.job_report.llm_tokens_usage
        assert captured is not None
        assert captured.nb_tokens_by_category == {TokenCategory.INPUT: 120, TokenCategory.OUTPUT: 47}

    @pytest.mark.asyncio
    async def test_worker_gen_text_no_usage_leaves_empty(self, mocker: MockerFixture) -> None:
        """Pins today's behavior: a response with no ``usage`` leaves nb_tokens_by_category empty.

        The job still carries a truthy tokens_usage, so a zero-token UsageReportEvent is later
        emitted — the documented silent under-count. This test pins the capture side of it.
        """
        worker = _make_worker(mocker, _make_text_response(mocker, usage=None))
        llm_job = _make_llm_job_with_empty_usage()

        await worker._gen_text(llm_job=llm_job)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        captured = llm_job.job_report.llm_tokens_usage
        assert captured is not None
        assert captured.nb_tokens_by_category == {}
