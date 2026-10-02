from pipelex.cogt.judgment.judgment_job import JudgmentJob, JudgmentJobParams
from pipelex.cogt.judgment.judgment_models import JudgmentQuestion, JudgmentState
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.system.job_metadata import JobCategory, JobMetadata


class JudgmentJobFactory:
    @classmethod
    def make_judgment_job(
        cls,
        *,
        state: JudgmentState,
        questions: dict[str, JudgmentQuestion],
        judgment_setting: JudgmentSetting,
        job_metadata: JobMetadata,
    ) -> JudgmentJob:
        job_metadata.job_category = JobCategory.JUDGMENT_JOB
        job_params = JudgmentJobParams(judgment_setting=judgment_setting)
        return JudgmentJob(
            job_metadata=job_metadata,
            state=state,
            questions=questions,
            job_params=job_params,
        )
