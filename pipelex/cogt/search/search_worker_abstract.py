from abc import ABC, abstractmethod
from typing import Any

from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.core.stuffs.search_result_content import SearchResultContent


class SearchWorkerAbstract(ABC):
    @abstractmethod
    async def search_sourced_answer(
        self,
        query: str,
        search_setting: SearchSetting,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> SearchResultContent:
        """Execute a search query and return a sourced answer with sources.

        Args:
            query: The search query text
            search_setting: Search configuration including model, depth, etc.
            include_domains: Optional list of domains to restrict search to
            exclude_domains: Optional list of domains to exclude from search
            from_date: Optional start date filter (YYYY-MM-DD)
            to_date: Optional end date filter (YYYY-MM-DD)

        Returns:
            SearchResultContent with answer and sources
        """

    @abstractmethod
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
        """Execute a search query and return structured data matching the schema.

        Args:
            query: The search query text
            search_setting: Search configuration including model, depth, etc.
            output_schema: Pydantic model class defining the expected output structure
            include_domains: Optional list of domains to restrict search to
            exclude_domains: Optional list of domains to exclude from search
            from_date: Optional start date filter (YYYY-MM-DD)
            to_date: Optional end date filter (YYYY-MM-DD)

        Returns:
            Dictionary matching the output_schema structure
        """
