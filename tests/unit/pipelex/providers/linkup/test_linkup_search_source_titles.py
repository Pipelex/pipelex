from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from linkup import LinkupSource, LinkupSourcedAnswer

from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.search.search_job_factory import SearchJobFactory
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.providers.linkup.linkup_search_worker import LinkupSearchWorker
from pipelex.system.job_metadata import JobMetadata, RunMetadata

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.core.stuffs.search_result_content import SearchResultContent

SOURCE_URL = "https://example.com/e-invoicing"


async def _search_with_source(mocker: MockerFixture, *, source: LinkupSource) -> SearchResultContent:
    linkup_client = mocker.patch("pipelex.providers.linkup.linkup_search_worker.LinkupClient").return_value
    linkup_client.async_search = mocker.AsyncMock(return_value=LinkupSourcedAnswer(answer="E-invoicing becomes mandatory.", sources=[source]))
    model = InferenceModelSpec(
        backend_name="linkup",
        name="linkup-standard",
        sdk="linkup",
        model_type=ModelType.SEARCH,
        model_id="standard",
        inputs=["text"],
        outputs=["sourced-answers", "structured"],
        costs={CostCategory.INPUT: 0.005, CostCategory.OUTPUT: 0.0},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )
    worker = LinkupSearchWorker(inference_model=model, api_key="test-key")
    search_job = SearchJobFactory.make_search_job(
        "French B2B e-invoicing requirements",
        search_setting=SearchSetting(model="linkup-standard"),
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id="plr-linkup-titles"),
            pipe_code="some_pipe",
        ),
    )
    return await worker.search_sourced_answer(search_job=search_job)


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
            ("Writing &amp;amp; in HTML", "Writing &amp; in HTML"),
            ("E-Invoicing in France: The 2026 Timeline", "E-Invoicing in France: The 2026 Timeline"),
        ],
        ids=["a named reference", "a numeric reference", "a reference decoded once", "a title with no reference"],
    )
    async def test_a_source_title_is_decoded_once_into_plain_text(self, mocker: MockerFixture, sent_title: str, expected_title: str) -> None:
        """Linkup can send a title with its page's HTML character references encoded; the result holds it decoded once."""
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
