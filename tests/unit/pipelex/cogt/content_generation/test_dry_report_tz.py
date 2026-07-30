"""Pin that the dry synthetic-job reporting copes with both naive and aware ``started_at``.

The synthetic ``completed_at`` must share the tzinfo of the incoming
``started_at`` so ``JobMetadata.duration`` can subtract them without crossing
naive and aware datetimes (which raises ``TypeError``). Callers in the codebase
do construct aware datetimes (e.g. ``pipe_abstract.py``), so the dry path must
not crash when one of those flows in.
"""

from datetime import UTC, datetime

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.dry_mock import report_dry_llm_job
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.system.job_metadata import JobMetadata


class TestDryReportTimezone:
    @pytest.mark.parametrize(
        "started_at",
        [
            pytest.param(datetime(2020, 1, 1, 10, 0, 0), id="naive"),
            pytest.param(datetime(2020, 1, 1, 10, 0, 0, tzinfo=UTC), id="aware_utc"),
            pytest.param(None, id="none_uses_default_factory"),
        ],
    )
    def test_duration_is_finite_for_any_started_at_tz(
        self,
        started_at: datetime | None,
        mocker: MockerFixture,
    ) -> None:
        captured_jobs: list[LLMJob] = []

        def _capture(inference_job: LLMJob) -> None:
            captured_jobs.append(inference_job)

        mock_delegate = mocker.MagicMock()
        mock_delegate.report_inference_job.side_effect = _capture
        # Patch get_report_delegate where it is looked up at call time (dry_mock).
        mocker.patch(
            "pipelex.cogt.content_generation.dry_mock.get_report_delegate",
            return_value=mock_delegate,
        )

        job_metadata = JobMetadata(
            user_id="test_user",
            pipeline_run_id="run_dry_tz",
            started_at=started_at,
        )

        report_dry_llm_job(
            job_metadata=job_metadata,
            llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
            llm_prompt=LLMPrompt(),
        )

        assert len(captured_jobs) == 1
        reported_metadata = captured_jobs[0].job_metadata
        duration = reported_metadata.duration
        assert duration is not None
        assert duration >= 0.0
