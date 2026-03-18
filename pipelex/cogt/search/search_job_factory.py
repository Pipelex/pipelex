from pipelex.cogt.search.search_job import SearchJob
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata


class SearchJobFactory:
    @classmethod
    def make_search_job(cls, job_metadata: JobMetadata) -> SearchJob:
        job_metadata.job_category = JobCategory.SEARCH_JOB
        return SearchJob(job_metadata=job_metadata)
