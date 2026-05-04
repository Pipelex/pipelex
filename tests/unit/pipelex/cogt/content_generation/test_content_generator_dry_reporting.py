"""Pin that ContentGeneratorDry invokes report_inference_job with a synthetic LLMJob.

This is a Phase-2 prerequisite for the Phase-6 e2e cross-worker emission tier:
without the dry generator emitting a UsageReportEvent, the Tier 8 assertions in
.claude/skills/temporal-e2e-validate/SKILL.md cannot run dry — they would have
to require live LLM calls to observe the runner-side fallback.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.pipeline.job_metadata import JobMetadata


class TestContentGeneratorDryReporting:
    """Pin the ContentGeneratorDry → ReportingManager.report_inference_job hook."""

    @pytest.mark.asyncio
    async def test_make_llm_text_invokes_report_inference_job(self, mocker: MockerFixture) -> None:
        """make_llm_text builds a synthetic LLMJob and reports it through get_report_delegate()."""
        captured_jobs: list[LLMJob] = []

        def _capture(inference_job: LLMJob) -> None:
            captured_jobs.append(inference_job)

        mock_delegate = mocker.MagicMock()
        mock_delegate.report_inference_job.side_effect = _capture
        mocker.patch(
            "pipelex.cogt.content_generation.content_generator_dry.get_report_delegate",
            return_value=mock_delegate,
        )

        generator = ContentGeneratorDry()
        job_metadata = JobMetadata(
            user_id="test_user",
            pipeline_run_id="run_dry_001",
        )
        llm_setting = LLMSetting(model="gpt-4o", temperature=0.5)
        llm_prompt = LLMPrompt()

        await generator.make_llm_text(
            job_metadata=job_metadata,
            llm_setting_main=llm_setting,
            llm_prompt_for_text=llm_prompt,
        )

        assert len(captured_jobs) == 1
        reported_job = captured_jobs[0]
        assert isinstance(reported_job, LLMJob)
        assert reported_job.job_metadata.pipeline_run_id == "run_dry_001"
        assert reported_job.job_report.llm_tokens_usage is not None
