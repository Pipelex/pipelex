"""Unit tests for the ``run_mode == DRY`` branch in the LLM text leaf (llm_generate).

The leaf is the single point where direct execution and the Temporal activities converge, so a DRY
branch there mocks identically on both backends. Contract: under DRY the worker is never touched
(no provider, no spend), the result carries the ``DRY RUN:`` marker, and exactly one synthetic
usage event is reported. The internal ``is_mock_usage`` sub-flag selects the reporting payload:
zero-token under the ``dry_run`` sentinel by default (cost report suppressed), non-zero under the
``mock_usage`` sentinel when set (cost report renders).
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import LLMAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.dry_mock import (
    DRY_RUN_INFERENCE_MODEL_NAME,
    MOCK_USAGE_MODEL_NAME,
    MOCK_USAGE_NB_TOKENS_BY_CATEGORY,
)
from pipelex.cogt.content_generation.llm_generate import llm_gen_text
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


class TestLlmGenerateDryBranch:
    def _assignment(self, *, run_mode: PipeRunMode, is_mock_usage: bool = False) -> LLMAssignment:
        return LLMAssignment(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_dry_branch"),
            cogt_run_params=CogtRunParams(run_mode=run_mode, is_mock_usage=is_mock_usage),
            llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
            llm_prompt=LLMPrompt(),
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("is_mock_usage", [False, True])
    async def test_dry_mode_routes_to_dry_mock_and_skips_worker(self, mocker: MockerFixture, is_mock_usage: bool) -> None:
        """run_mode=DRY -> the dry helper answers with the marker string; get_llm_worker is never
        called — regardless of the is_mock_usage sub-flag (it only changes reporting).
        """
        worker_spy = mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker")
        mock_delegate = mocker.MagicMock()
        mocker.patch("pipelex.cogt.content_generation.dry_mock.get_report_delegate", return_value=mock_delegate)

        result = await llm_gen_text(self._assignment(run_mode=PipeRunMode.DRY, is_mock_usage=is_mock_usage))

        worker_spy.assert_not_called()
        assert result.startswith("DRY RUN:")

    @pytest.mark.asyncio
    async def test_dry_mode_reports_one_zero_token_job(self, mocker: MockerFixture) -> None:
        """Default dry leaf reports exactly one synthetic job, zero-token under the dry_run sentinel (suppressed)."""
        mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker")
        mock_delegate = mocker.MagicMock()
        mocker.patch("pipelex.cogt.content_generation.dry_mock.get_report_delegate", return_value=mock_delegate)

        await llm_gen_text(self._assignment(run_mode=PipeRunMode.DRY))

        assert mock_delegate.report_inference_job.call_count == 1
        reported_job = mock_delegate.report_inference_job.call_args.kwargs["inference_job"]
        usage = reported_job.job_report.llm_tokens_usage
        assert usage is not None
        assert usage.inference_model_name == DRY_RUN_INFERENCE_MODEL_NAME
        aggregated = CostRegistry.aggregate_costs([usage])
        assert not aggregated.has_reportable_usage
        assert aggregated.total_nb_tokens == 0

    @pytest.mark.asyncio
    async def test_mock_usage_reports_one_non_zero_job(self, mocker: MockerFixture) -> None:
        """is_mock_usage=True -> exactly one synthetic job, non-zero sentinel counts under the
        mock_usage sentinel, so the aggregated usage is reportable (cost report renders).
        """
        worker_spy = mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker")
        mock_delegate = mocker.MagicMock()
        mocker.patch("pipelex.cogt.content_generation.dry_mock.get_report_delegate", return_value=mock_delegate)

        await llm_gen_text(self._assignment(run_mode=PipeRunMode.DRY, is_mock_usage=True))

        worker_spy.assert_not_called()
        assert mock_delegate.report_inference_job.call_count == 1
        reported_job = mock_delegate.report_inference_job.call_args.kwargs["inference_job"]
        usage = reported_job.job_report.llm_tokens_usage
        assert usage is not None
        assert usage.inference_model_name == MOCK_USAGE_MODEL_NAME
        aggregated = CostRegistry.aggregate_costs([usage])
        assert aggregated.has_reportable_usage
        assert aggregated.total_nb_tokens == sum(MOCK_USAGE_NB_TOKENS_BY_CATEGORY.values())

    @pytest.mark.asyncio
    async def test_live_mode_uses_real_worker(self, mocker: MockerFixture) -> None:
        """run_mode=LIVE -> the real worker path runs and no synthetic job is reported."""
        worker = mocker.MagicMock()
        worker.gen_text = mocker.AsyncMock(return_value="real generated text")
        worker_spy = mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker", return_value=worker)
        report_spy = mocker.patch("pipelex.cogt.content_generation.dry_mock.get_report_delegate", return_value=mocker.MagicMock())

        result = await llm_gen_text(self._assignment(run_mode=PipeRunMode.LIVE))

        worker_spy.assert_called_once()
        assert result == "real generated text"
        report_spy.assert_not_called()
