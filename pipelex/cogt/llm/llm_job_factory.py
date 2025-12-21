from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.config import get_config
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata


class LLMJobFactory:
    @classmethod
    def make_llm_job(
        cls,
        llm_prompt: LLMPrompt,
        job_metadata: JobMetadata,
        llm_job_params: LLMJobParams,
        llm_job_config: LLMJobConfig | None = None,
    ) -> LLMJob:
        config = get_config()
        llm_config = config.cogt.llm_config
        job_metadata.job_category = JobCategory.LLM_JOB
        job_params = llm_job_params
        job_config = llm_job_config or llm_config.llm_job_config

        return LLMJob(
            job_metadata=job_metadata,
            llm_prompt=llm_prompt,
            job_params=job_params,
            job_config=job_config,
        )
