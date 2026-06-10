"""Unit tests for the shared leaf-level mock helpers (dry_mock).

The load-bearing contract: a ``--mock-inference`` synthetic LLM job carries *non-zero* tokens so it is
reportable (``AggregatedCosts.has_reportable_usage`` True → a cost report renders), while a ``--dry-run``
synthetic job carries zero tokens and stays non-reportable (the report is suppressed). This is the durable
reason the two modes diverge at the reporting layer.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import LLMAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.dry_mock import (
    DRY_RUN_INFERENCE_MODEL_NAME,
    MOCK_INFERENCE_MODEL_NAME,
    mock_llm_gen_text,
    report_dry_llm_job,
    report_mock_inference_llm_job,
)
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.usage.cost_registry import CostRegistry
from pipelex.pipeline.job_metadata import JobMetadata


class TestDryMock:
    def _capture_reported_job(self, mocker: MockerFixture) -> list[LLMJob]:
        """Patch get_report_delegate in dry_mock and capture every reported LLMJob."""
        captured: list[LLMJob] = []

        def _capture(inference_job: LLMJob) -> None:
            captured.append(inference_job)

        mock_delegate = mocker.MagicMock()
        mock_delegate.report_inference_job.side_effect = _capture
        mocker.patch("pipelex.cogt.content_generation.dry_mock.get_report_delegate", return_value=mock_delegate)
        return captured

    def test_mock_inference_job_is_reportable_non_zero(self, mocker: MockerFixture) -> None:
        """report_mock_inference_llm_job emits non-zero usage under the mock_inference sentinel -> reportable."""
        captured = self._capture_reported_job(mocker)
        report_mock_inference_llm_job(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_mock"),
            llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
            llm_prompt=LLMPrompt(),
        )

        assert len(captured) == 1
        usage = captured[0].job_report.llm_tokens_usage
        assert usage is not None
        assert usage.inference_model_name == MOCK_INFERENCE_MODEL_NAME
        aggregated = CostRegistry.aggregate_costs([usage])
        assert aggregated.has_reportable_usage  # the whole point: a cost report will render
        assert aggregated.total_nb_tokens > 0

    def test_dry_job_is_zero_and_not_reportable(self, mocker: MockerFixture) -> None:
        """report_dry_llm_job stays zero-token under the dry_run sentinel -> NOT reportable (suppressed)."""
        captured = self._capture_reported_job(mocker)
        report_dry_llm_job(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_dry"),
            llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
            llm_prompt=LLMPrompt(),
        )

        assert len(captured) == 1
        usage = captured[0].job_report.llm_tokens_usage
        assert usage is not None
        assert usage.inference_model_name == DRY_RUN_INFERENCE_MODEL_NAME
        aggregated = CostRegistry.aggregate_costs([usage])
        assert not aggregated.has_reportable_usage  # dry runs are deliberately suppressed
        assert aggregated.total_nb_tokens == 0

    @pytest.mark.asyncio
    async def test_mock_llm_gen_text_returns_synthetic_text_and_reports(self, mocker: MockerFixture) -> None:
        """mock_llm_gen_text returns a synthetic string and reports one reportable usage event."""
        captured = self._capture_reported_job(mocker)
        assignment = LLMAssignment(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_text", is_mock_inference=True),
            cogt_run_params=CogtRunParams(),
            llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
            llm_prompt=LLMPrompt(),
        )

        result = mock_llm_gen_text(assignment)

        assert result.startswith("MOCK INFERENCE")
        assert len(captured) == 1
        assert captured[0].job_report.llm_tokens_usage is not None
