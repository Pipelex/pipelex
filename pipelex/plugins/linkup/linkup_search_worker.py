from datetime import date
from typing import Any

from linkup import LinkupClient, LinkupSourcedAnswer
from typing_extensions import override

from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.core.stuffs.search_result_content import SearchResultContent, SearchSourceContent
from pipelex.hub import get_secrets_provider


class LinkupSearchWorker(SearchWorkerAbstract):
    def __init__(self) -> None:
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
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> SearchResultContent:
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
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
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

        # If response is a Pydantic model, convert to dict
        if hasattr(response, "model_dump"):
            result: dict[str, Any] = response.model_dump()
            return result
        return dict(response)  # type: ignore[arg-type]
