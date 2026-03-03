import pytest
from pydantic import BaseModel

from pipelex import pretty_print
from pipelex.cogt.search.search_depth import SearchDepth
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.cogt.search.search_worker_factory import get_search_worker
from tests.integration.pipelex.cogt.test_data import SearchTestCases


class TopicSummary(BaseModel):
    title: str
    summary: str
    key_points: list[str]


@pytest.mark.search
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestSearch:
    @pytest.mark.parametrize(
        ("topic", "query"),
        SearchTestCases.SOURCED_ANSWER_QUERIES,
    )
    async def test_search_sourced_answer(self, topic: str, query: str) -> None:
        """Verify that search_sourced_answer returns a non-empty answer with sources."""
        worker = get_search_worker("linkup/standard")
        search_setting = SearchSetting(
            model="linkup/standard",
            depth=SearchDepth.STANDARD,
        )
        result = await worker.search_sourced_answer(
            query=query,
            search_setting=search_setting,
        )
        pretty_print(result, title=f"Sourced Answer Result ({topic})")
        assert result.answer, "Expected a non-empty answer"
        assert len(result.sources) > 0, "Expected at least one source"
        for source in result.sources:
            assert source.name, "Expected source to have a name"
            assert source.url, "Expected source to have a URL"

    @pytest.mark.parametrize(
        ("topic", "query"),
        SearchTestCases.STRUCTURED_QUERIES,
    )
    async def test_search_structured(self, topic: str, query: str) -> None:
        """Verify that search_structured returns a dict with the expected schema keys."""
        worker = get_search_worker("linkup/standard")
        search_setting = SearchSetting(
            model="linkup/standard",
            depth=SearchDepth.STANDARD,
        )
        result = await worker.search_structured(
            query=query,
            search_setting=search_setting,
            output_schema=TopicSummary,
        )
        pretty_print(result, title=f"Structured Search Result ({topic})")
        assert isinstance(result, dict), "Expected a dict result"
        assert "data" in result, "Expected 'data' key in result"
        assert "sources" in result, "Expected 'sources' key in result"
        data = result["data"]
        assert "title" in data, "Expected 'title' key in data"
        assert "summary" in data, "Expected 'summary' key in data"
        assert "key_points" in data, "Expected 'key_points' key in data"
        assert len(result["sources"]) > 0, "Expected at least one source"
