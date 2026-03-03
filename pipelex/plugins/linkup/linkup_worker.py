from datetime import date
from typing import Any

from linkup import LinkupClient, LinkupFetchResponse, LinkupSourcedAnswer
from typing_extensions import override

from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.search.fetch_worker_abstract import FetchWorkerAbstract
from pipelex.cogt.search.search_job_factory import FetchJobFactory, SearchJobFactory
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.search_result_content import SearchResultContent, SearchSourceContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_secrets_provider
from pipelex.pipeline.job_metadata import JobMetadata, UnitJobId
from pipelex.reporting.reporting_protocol import ReportingProtocol


class LinkupWorker(SearchWorkerAbstract, FetchWorkerAbstract):
    def __init__(
        self,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ) -> None:
        SearchWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)
        FetchWorkerAbstract.__init__(self, reporting_delegate=reporting_delegate)
        self.inference_model = inference_model
        api_key = get_secrets_provider().get_secret(secret_id="LINKUP_API_KEY")
        self._linkup_client = LinkupClient(api_key=api_key)

    def _parse_date(self, date_str: str | None) -> date | None:
        if date_str is None:
            return None
        return date.fromisoformat(date_str)

    @override
    async def search_sourced_answer(
        self,
        query: str,
        search_setting: SearchSetting,
        job_metadata: JobMetadata,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> SearchResultContent:
        job_metadata.unit_job_id = UnitJobId.SEARCH_SOURCED_ANSWER
        search_job = SearchJobFactory.make_search_job(job_metadata=job_metadata)
        search_job.search_job_before_start(inference_model=self.inference_model)

        depth_value = search_setting.depth
        response: LinkupSourcedAnswer = await self._linkup_client.async_search(
            query=query,
            depth=depth_value,  # type: ignore[arg-type]
            output_type="sourcedAnswer",
            include_images=search_setting.include_images,
            include_inline_citations=search_setting.include_inline_citations,
            max_results=search_setting.max_results,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            from_date=self._parse_date(from_date),
            to_date=self._parse_date(to_date),
        )

        # Per-request cost model: costs are defined per million, so 1 request = 1_000_000
        if search_tokens_usage := search_job.job_report.search_tokens_usage:
            search_tokens_usage.nb_tokens_by_category = {TokenCategory.INPUT: 1_000_000, TokenCategory.OUTPUT: 1_000_000}
        search_job.search_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=search_job)

        sources: list[SearchSourceContent] = []
        for source in response.sources:
            sources.append(
                SearchSourceContent(
                    name=source.name,
                    url=source.url,
                    snippet=source.snippet,
                )
            )

        return SearchResultContent(
            answer=response.answer,
            sources=sources,
        )

    @override
    async def search_structured(
        self,
        query: str,
        search_setting: SearchSetting,
        output_schema: type,
        job_metadata: JobMetadata,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        job_metadata.unit_job_id = UnitJobId.SEARCH_STRUCTURED
        search_job = SearchJobFactory.make_search_job(job_metadata=job_metadata)
        search_job.search_job_before_start(inference_model=self.inference_model)

        depth_value = search_setting.depth
        response = await self._linkup_client.async_search(
            query=query,
            depth=depth_value,  # type: ignore[arg-type]
            output_type="structured",
            structured_output_schema=output_schema,
            include_images=search_setting.include_images,
            max_results=search_setting.max_results,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            from_date=self._parse_date(from_date),
            to_date=self._parse_date(to_date),
            include_sources=True,
        )

        # Per-request cost model: costs are defined per million, so 1 request = 1_000_000
        if search_tokens_usage := search_job.job_report.search_tokens_usage:
            search_tokens_usage.nb_tokens_by_category = {TokenCategory.INPUT: 1_000_000, TokenCategory.OUTPUT: 1_000_000}
        search_job.search_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=search_job)

        # If response is a Pydantic model, convert to dict
        if hasattr(response, "model_dump"):
            result: dict[str, Any] = response.model_dump()
            return result
        return dict(response)  # type: ignore[arg-type]

    @override
    async def fetch_url(
        self,
        url: str,
        job_metadata: JobMetadata,
        include_raw_html: bool | None = None,
        render_js: bool | None = None,
        extract_images: bool | None = None,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> TextAndImagesContent:
        job_metadata.unit_job_id = UnitJobId.FETCH_URL
        fetch_job = FetchJobFactory.make_fetch_job(job_metadata=job_metadata)
        fetch_job.fetch_job_before_start(inference_model=self.inference_model)

        response: LinkupFetchResponse = await self._linkup_client.async_fetch(
            url=url,
            include_raw_html=include_raw_html,
            render_js=render_js,
            extract_images=extract_images,
            timeout=timeout,
        )

        # Per-request cost model: costs are defined per million, so 1 request = 1_000_000
        if fetch_tokens_usage := fetch_job.job_report.fetch_tokens_usage:
            fetch_tokens_usage.nb_tokens_by_category = {TokenCategory.INPUT: 1_000_000, TokenCategory.OUTPUT: 1_000_000}
        fetch_job.fetch_job_after_complete()
        if self.reporting_delegate:
            self.reporting_delegate.report_inference_job(inference_job=fetch_job)

        text = TextContent(text=response.markdown) if response.markdown else None

        images: list[ImageContent] | None = None
        if response.images is not None:
            images = [
                ImageContent(
                    url=image.url,
                    caption=image.alt or None,
                )
                for image in response.images
            ]

        return TextAndImagesContent(
            text=text,
            images=images or None,
            raw_html=response.raw_html,
        )
