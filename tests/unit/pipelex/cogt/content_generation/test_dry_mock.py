"""Unit tests for the shared leaf-level mock helpers (dry_mock).

The load-bearing contract: an ``is_mock_usage`` synthetic LLM job carries *non-zero* tokens so it is
reportable (``AggregatedCosts.has_reportable_usage`` True → a cost report renders), while the default
dry synthetic job carries zero tokens and stays non-reportable (the report is suppressed). This is the
durable reason the sub-flag exists at the reporting layer.
"""

from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.dry_mock import (
    DRY_RUN_INFERENCE_MODEL_NAME,
    MOCK_USAGE_MODEL_NAME,
    report_dry_llm_job,
    report_mock_usage_llm_job,
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

    def test_mock_usage_job_is_reportable_non_zero(self, mocker: MockerFixture) -> None:
        """report_mock_usage_llm_job emits non-zero usage under the mock_usage sentinel -> reportable."""
        captured = self._capture_reported_job(mocker)
        report_mock_usage_llm_job(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_mock"),
            llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
            llm_prompt=LLMPrompt(),
        )

        assert len(captured) == 1
        usage = captured[0].job_report.llm_tokens_usage
        assert usage is not None
        assert usage.inference_model_name == MOCK_USAGE_MODEL_NAME
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
