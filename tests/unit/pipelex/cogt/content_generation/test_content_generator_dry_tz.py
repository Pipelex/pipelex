"""Pin that the dry generator copes with both naive and aware ``started_at``.

The synthetic ``completed_at`` must share the tzinfo of the incoming
``started_at`` so ``JobMetadata.duration`` can subtract them without crossing
naive and aware datetimes (which raises ``TypeError``). Callers in the codebase
do construct aware datetimes (e.g. ``pipe_abstract.py``), so the dry path must
not crash when one of those flows in.
"""

from datetime import datetime, timezone

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.pipeline.job_metadata import JobMetadata


class TestContentGeneratorDryTimezone:
    @pytest.mark.parametrize(
        "started_at",
        [
            pytest.param(datetime(2020, 1, 1, 10, 0, 0), id="naive"),
            pytest.param(datetime(2020, 1, 1, 10, 0, 0, tzinfo=timezone.utc), id="aware_utc"),
            pytest.param(None, id="none_uses_default_factory"),
        ],
    )
    @pytest.mark.asyncio
    async def test_duration_is_finite_for_any_started_at_tz(
        self,
        started_at: datetime | None,
        mocker: MockerFixture,
    ) -> None:
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
            pipeline_run_id="run_dry_tz",
            started_at=started_at,
        )
        llm_setting = LLMSetting(model="gpt-4o", temperature=0.5)
        llm_prompt = LLMPrompt()

        await generator.make_llm_text(
            job_metadata=job_metadata,
            llm_setting_main=llm_setting,
            llm_prompt_for_text=llm_prompt,
        )

        assert len(captured_jobs) == 1
        reported_metadata = captured_jobs[0].job_metadata
        duration = reported_metadata.duration
        assert duration is not None
        assert duration >= 0.0
