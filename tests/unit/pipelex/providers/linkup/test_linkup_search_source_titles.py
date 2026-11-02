from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from linkup import LinkupSource, LinkupSourcedAnswer

from tests.unit.pipelex.providers.linkup.linkup_test_helpers import linkup_search_job, linkup_search_worker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.core.stuffs.search_result_content import SearchResultContent

SOURCE_URL = "https://example.com/e-invoicing"


async def _search_with_source(mocker: MockerFixture, *, source: LinkupSource) -> SearchResultContent:
    worker = linkup_search_worker(mocker, response=LinkupSourcedAnswer(answer="E-invoicing becomes mandatory.", sources=[source]))
    return await worker.search_sourced_answer(search_job=linkup_search_job(query="French B2B e-invoicing requirements"))


@pytest.mark.asyncio(loop_scope="class")
class TestLinkupSearchSourceTitles:
    @pytest.mark.parametrize(
        ("sent_title", "expected_title"),
        [
            (
                "France B2B E-Invoicing: Requirements &amp; SAP Integration",
                "France B2B E-Invoicing: Requirements & SAP Integration",
            ),
            ("The Buyer&#39;s Guide to E-Invoicing", "The Buyer's Guide to E-Invoicing"),
            ("The Buyer&#x27;s Guide to E-Invoicing", "The Buyer's Guide to E-Invoicing"),
            ("Writing &amp;amp; in HTML", "Writing &amp; in HTML"),
            ("E-Invoicing&nbsp;in France", "E-Invoicing in France"),
            ("Health &notable", "Health &notable"),
            ("R&D &copy editing", "R&D &copy editing"),
            ("Health &notable; and more", "Health &notable; and more"),
            ("E-Invoicing in France: The 2026 Timeline", "E-Invoicing in France: The 2026 Timeline"),
        ],
        ids=[
            "a named reference",
            "a decimal reference",
            "a hexadecimal reference",
            "a reference decoded once",
            "a no-break space becomes a space",
            "an ampersand starting no reference",
            "references without their semicolon",
            "an unknown named reference",
            "a title with no reference",
        ],
    )
    async def test_a_source_title_is_decoded_once_into_plain_text(self, mocker: MockerFixture, sent_title: str, expected_title: str) -> None:
        """Only complete references, ending in `;`, are decoded, once, and a no-break space becomes an ordinary space."""
        result = await _search_with_source(mocker, source=LinkupSource(name=sent_title, url=SOURCE_URL, snippet="Mandatory from 2026."))

        (document,) = result.sources
        assert document.title == expected_title
        assert document.url == SOURCE_URL

    async def test_a_source_snippet_is_left_as_sent(self, mocker: MockerFixture) -> None:
        """A snippet is the page's extracted text, so a reference it quotes stays as written."""
        sent_snippet = "Escape an ampersand as &amp; in HTML."

        result = await _search_with_source(mocker, source=LinkupSource(name="HTML entities", url=SOURCE_URL, snippet=sent_snippet))

        (document,) = result.sources
        assert document.snippet == sent_snippet
