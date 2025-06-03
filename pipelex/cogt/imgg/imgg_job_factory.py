from typing import Optional

from pipelex.cogt.imgg.imgg_job import ImggJob
from pipelex.cogt.imgg.imgg_job_components import ImggJobConfig, ImggJobParams, ImggJobReport
from pipelex.cogt.imgg.imgg_prompt import ImggPrompt
from pipelex.config import get_config
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata


class ImggJobFactory:
    # straightforward: the prompt is provided

    @classmethod
    def make_imgg_job_from_prompt(
        cls,
        imgg_prompt: ImggPrompt,
        imgg_job_params: Optional[ImggJobParams] = None,
        imgg_job_config: Optional[ImggJobConfig] = None,
        job_metadata: Optional[JobMetadata] = None,
    ) -> ImggJob:
        config = get_config()
        imgg_config = get_config().cogt.imgg_config
        job_metadata = job_metadata or JobMetadata(
            top_job_id=f"IMGGJob for {config.project_name}",
            job_category=JobCategory.IMGG_JOB,
        )
        job_params = imgg_job_params or imgg_config.make_default_imgg_job_params()
        job_config = imgg_job_config or imgg_config.imgg_job_config
        job_report = ImggJobReport()

        return ImggJob(
            job_metadata=job_metadata,
            imgg_prompt=imgg_prompt,
            job_params=job_params,
            job_config=job_config,
            job_report=job_report,
        )

    @classmethod
    def make_imgg_job_from_prompt_contents(
        cls,
        positive_text: str,
        imgg_job_params: Optional[ImggJobParams] = None,
        imgg_job_config: Optional[ImggJobConfig] = None,
        job_metadata: Optional[JobMetadata] = None,
    ) -> ImggJob:
        config = get_config()
        imgg_config = get_config().cogt.imgg_config
        job_metadata = job_metadata or JobMetadata(
            top_job_id=f"IMGGJob for {config.project_name}",
            job_category=JobCategory.IMGG_JOB,
        )
        imgg_prompt = ImggPrompt(positive_text=positive_text)
        job_params = imgg_job_params or imgg_config.make_default_imgg_job_params()
        job_config = imgg_job_config or imgg_config.imgg_job_config
        job_report = ImggJobReport()

        return ImggJob(
            job_metadata=job_metadata,
            imgg_prompt=imgg_prompt,
            job_params=job_params,
            job_config=job_config,
            job_report=job_report,
        )
