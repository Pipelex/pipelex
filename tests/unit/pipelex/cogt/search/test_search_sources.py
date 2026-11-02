import pytest

from pipelex.cogt.search.search_sources import deduplicate_search_sources
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from tests.unit.pipelex.cogt.search.test_data import SearchSourcesTestData


def _search_result(*, sources: list[tuple[str, str]], answer: str) -> SearchResultContent:
    return SearchResultContent(
        answer=answer,
        sources=[DocumentContent(url=url, public_url=url, title=title, mime_type="text/html") for url, title in sources],
    )


class TestSearchSources:
    @pytest.mark.parametrize(
        ("topic", "sources", "answer", "renumber_citations"),
        SearchSourcesTestData.NO_DUPLICATE_CASES,
    )
    def test_a_result_without_a_repeated_address_comes_back_unchanged(
        self,
        topic: str,
        sources: list[tuple[str, str]],
        answer: str,
        renumber_citations: bool,
    ) -> None:
        """Nothing to drop means nothing to renumber: the result is the one the provider's worker built."""
        search_result = _search_result(sources=sources, answer=answer)

        deduplicated = deduplicate_search_sources(search_result=search_result, renumber_citations=renumber_citations)

        assert deduplicated is search_result, topic
        assert deduplicated.answer == answer
        assert [source.url for source in deduplicated.sources] == [url for url, _ in sources]

    @pytest.mark.parametrize(
        ("topic", "sources", "answer", "renumber_citations", "expected_titles", "expected_answer"),
        SearchSourcesTestData.DEDUP_CASES,
    )
    def test_each_address_is_listed_once_and_citations_follow_their_source(
        self,
        topic: str,
        sources: list[tuple[str, str]],
        answer: str,
        renumber_citations: bool,
        expected_titles: list[str],
        expected_answer: str,
    ) -> None:
        """The first entry of each address is kept in the provider's order, and each citation points at its source's new position."""
        search_result = _search_result(sources=sources, answer=answer)

        deduplicated = deduplicate_search_sources(search_result=search_result, renumber_citations=renumber_citations)

        assert [source.title for source in deduplicated.sources] == expected_titles, topic
        assert deduplicated.answer == expected_answer, topic
        # The kept entries are the provider's own, fragment included, and the result handed in is left as it was
        kept_by_title = {title: url for url, title in sources}
        assert [source.url for source in deduplicated.sources] == [kept_by_title[title] for title in expected_titles]
        assert search_result.answer == answer
        assert len(search_result.sources) == len(sources)
