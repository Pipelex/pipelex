"""A Linkup sourced answer lists each source once, through the search path every provider's answer takes.

No provider is called: the SDK client is mocked, so this needs no inference marker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from linkup import LinkupSource, LinkupSourcedAnswer

from pipelex.cogt.search.search_job_factory import SearchJobFactory
from pipelex.cogt.search.search_setting import SearchSetting
from tests.unit.pipelex.providers.linkup.linkup_test_helpers import LINKUP_SEARCH_MODEL, linkup_job_metadata, linkup_search_worker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.providers.linkup.linkup_search_worker import LinkupSearchWorker

ALPHA_URL = "https://alpha.example.com/report"
BETA_URL = "https://beta.example.org/article"
ANSWER = "Alpha says so [1], Beta agrees [2], and Alpha's methods confirm it [3]."
RENUMBERED_ANSWER = "Alpha says so [1], Beta agrees [2], and Alpha's methods confirm it [1]."


def _linkup_worker(mocker: MockerFixture) -> LinkupSearchWorker:
    return linkup_search_worker(
        mocker,
        response=LinkupSourcedAnswer(
            answer=ANSWER,
            sources=[
                LinkupSource(name="Alpha", url=ALPHA_URL, snippet="Alpha's finding"),
                LinkupSource(name="Beta", url=BETA_URL, snippet="Beta's agreement"),
                LinkupSource(name="Alpha", url="http://www.alpha.example.com/report/#methods", snippet="Alpha's methods"),
            ],
        ),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestLinkupSearchSourceDedup:
    @pytest.mark.parametrize(
        ("include_inline_citations", "expected_answer"),
        [
            (True, RENUMBERED_ANSWER),
            (False, ANSWER),
        ],
        ids=["with inline citations", "without inline citations"],
    )
    async def test_a_sourced_answer_lists_each_address_once(
        self,
        mocker: MockerFixture,
        include_inline_citations: bool,
        expected_answer: str,
    ) -> None:
        """The entry naming the first page again, written another way, is dropped; citations are renumbered only when asked for."""
        worker = _linkup_worker(mocker)
        search_job = SearchJobFactory.make_search_job(
            "what does Alpha find",
            search_setting=SearchSetting(model=LINKUP_SEARCH_MODEL, include_inline_citations=include_inline_citations),
            job_metadata=linkup_job_metadata(),
        )

        search_result = await worker.search_sourced_answer(search_job=search_job)

        assert [(source.url, source.title, source.snippet) for source in search_result.sources] == [
            (ALPHA_URL, "Alpha", "Alpha's finding"),
            (BETA_URL, "Beta", "Beta's agreement"),
        ]
        assert search_result.answer == expected_answer
