from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobConfig, ImgGenJobParams, ImgGenJobReport
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.config import get_config
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata


class ImgGenJobFactory:
    @classmethod
    def make_img_gen_job_from_prompt(
        cls,
        img_gen_prompt: ImgGenPrompt,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
        job_metadata: JobMetadata | None = None,
    ) -> ImgGenJob:
        img_gen_config = get_config().cogt.img_gen_config
        job_metadata = job_metadata or JobMetadata(
            job_category=JobCategory.IMG_GEN_JOB,
        )
        job_params = img_gen_job_params or img_gen_config.make_default_img_gen_job_params()
        job_config = img_gen_job_config or img_gen_config.img_gen_job_config
        job_report = ImgGenJobReport()

        return ImgGenJob(
            job_metadata=job_metadata,
            img_gen_prompt=img_gen_prompt,
            job_params=job_params,
            job_config=job_config,
            job_report=job_report,
        )

    @classmethod
    def make_img_gen_job_from_prompt_contents(
        cls,
        positive_text: str,
        img_gen_job_params: ImgGenJobParams | None = None,
        img_gen_job_config: ImgGenJobConfig | None = None,
        job_metadata: JobMetadata | None = None,
    ) -> ImgGenJob:
        img_gen_config = get_config().cogt.img_gen_config
        job_metadata = job_metadata or JobMetadata(
            job_category=JobCategory.IMG_GEN_JOB,
        )
        img_gen_prompt = ImgGenPrompt(positive_text=positive_text)
        job_params = img_gen_job_params or img_gen_config.make_default_img_gen_job_params()
        job_config = img_gen_job_config or img_gen_config.img_gen_job_config
        job_report = ImgGenJobReport()

        return ImgGenJob(
            job_metadata=job_metadata,
            img_gen_prompt=img_gen_prompt,
            job_params=job_params,
            job_config=job_config,
            job_report=job_report,
        )
