from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams, ExtractJobReport
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata


class ExtractJobFactory:
    @classmethod
    def make_extract_job(
        cls,
        extract_input: ExtractInput,
        extract_job_params: ExtractJobParams | None = None,
        extract_job_config: ExtractJobConfig | None = None,
        job_metadata: JobMetadata | None = None,
    ) -> ExtractJob:
        # TODO: manage the param default through the config
        job_metadata = job_metadata or JobMetadata(
            job_category=JobCategory.EXTRACT_JOB,
        )
        job_params = extract_job_params or ExtractJobParams.make_default_extract_job_params()
        job_config = extract_job_config or ExtractJobConfig()
        job_report = ExtractJobReport()

        return ExtractJob(
            job_metadata=job_metadata,
            extract_input=extract_input,
            job_params=job_params,
            job_config=job_config,
            job_report=job_report,
        )
