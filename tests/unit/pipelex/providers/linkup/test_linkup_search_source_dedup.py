"""A Linkup sourced answer lists each source once, through the search path every provider's answer takes.

No provider is called: the SDK client is mocked, so this needs no inference marker.
"""

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

ALPHA_URL = "https://alpha.example.com/report"
BETA_URL = "https://beta.example.org/article"
ANSWER = "Alpha says so [1], Beta agrees [2], and Alpha's methods confirm it [3]."
RENUMBERED_ANSWER = "Alpha says so [1], Beta agrees [2], and Alpha's methods confirm it [1]."


def _linkup_worker(mocker: MockerFixture) -> LinkupSearchWorker:
    linkup_client = mocker.patch("pipelex.providers.linkup.linkup_search_worker.LinkupClient").return_value
    linkup_client.async_search = mocker.AsyncMock(
        return_value=LinkupSourcedAnswer(
            answer=ANSWER,
            sources=[
                LinkupSource(name="Alpha", url=ALPHA_URL, snippet="Alpha's finding"),
                LinkupSource(name="Beta", url=BETA_URL, snippet="Beta's agreement"),
                LinkupSource(name="Alpha", url="http://www.alpha.example.com/report/#methods", snippet="Alpha's methods"),
            ],
        )
    )
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
    return LinkupSearchWorker(inference_model=model, api_key="test-key")


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
            search_setting=SearchSetting(model="linkup-standard", include_inline_citations=include_inline_citations),
            job_metadata=JobMetadata(
                run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id="plr-linkup-dedup"),
                pipe_code="some_pipe",
            ),
        )

        search_result = await worker.search_sourced_answer(search_job=search_job)

        assert [(source.url, source.title, source.snippet) for source in search_result.sources] == [
            (ALPHA_URL, "Alpha", "Alpha's finding"),
            (BETA_URL, "Beta", "Beta's agreement"),
        ]
        assert search_result.answer == expected_answer
