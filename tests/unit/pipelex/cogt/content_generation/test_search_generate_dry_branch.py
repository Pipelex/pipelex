"""Unit tests for the ``run_mode == DRY`` branch in the search leaf (search_generate).

Contract: under DRY the sourced-answer leaf mints a full synthetic ``SearchResultContent`` (with
mock sources) without resolving any worker or touching the model deck; LIVE keeps the real path.
The structured-search DRY arm does schema codegen, so it is covered by the integration tests in
``tests/integration/pipelex/cogt/content_generation/test_leaf_dry_object_mocks.py``.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import SearchAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.search_generate import search_gen_sourced_answer
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.config import get_config
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


class TestSearchGenerateDryBranch:
    def _assignment(self, *, run_mode: PipeRunMode) -> SearchAssignment:
        return SearchAssignment(
            job_metadata=JobMetadata(storage_scope="test/scope", user_id="u", pipeline_run_id="run_search_dry"),
            cogt_run_params=CogtRunParams(run_mode=run_mode),
            query="what is pipelex?",
            search_setting=SearchSetting(model="mock-search-handle"),
        )

    @pytest.mark.asyncio
    async def test_dry_mints_result_without_worker(self, mocker: MockerFixture) -> None:
        """DRY: a synthetic SearchResultContent with mock sources; the model deck is never resolved."""
        deck_spy = mocker.patch("pipelex.cogt.content_generation.search_generate.get_model_deck")

        result = await search_gen_sourced_answer(self._assignment(run_mode=PipeRunMode.DRY))

        deck_spy.assert_not_called()
        assert isinstance(result, SearchResultContent)
        assert len(result.sources) == get_config().inference.dry_run.nb_list_items

    @pytest.mark.asyncio
    async def test_live_resolves_worker(self, mocker: MockerFixture) -> None:
        """LIVE keeps the real path: the worker is resolved from the deck and runs the search."""
        sentinel = mocker.MagicMock()
        worker = mocker.MagicMock()
        worker.search_sourced_answer = mocker.AsyncMock(return_value=sentinel)
        mocker.patch("pipelex.cogt.content_generation.search_generate._make_search_worker", return_value=worker)
        mocker.patch("pipelex.cogt.content_generation.search_generate._make_search_job", return_value=mocker.MagicMock())

        result = await search_gen_sourced_answer(self._assignment(run_mode=PipeRunMode.LIVE))

        worker.search_sourced_answer.assert_awaited_once()
        assert result is sentinel
