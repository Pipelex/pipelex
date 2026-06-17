from pipelex.cogt.search.search_job import SearchJob, SearchJobParams
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata


class SearchJobFactory:
    @classmethod
    def make_search_job(
        cls,
        query: str,
        *,
        search_setting: SearchSetting,
        job_metadata: JobMetadata,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> SearchJob:
        job_metadata.job_category = JobCategory.SEARCH_JOB
        job_params = SearchJobParams(
            search_setting=search_setting,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            from_date=from_date,
            to_date=to_date,
        )
        return SearchJob(
            job_metadata=job_metadata,
            query=query,
            job_params=job_params,
        )
