import pytest

from pipelex import log, pretty_print
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.search.search_job_factory import SearchJobFactory
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.cogt.search.search_worker_factory import SearchWorkerFactory
from pipelex.hub import get_model_deck
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


@pytest.mark.search
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestConfigCoverageSearch:
    async def test_search(self, search_combo: ModelCombo, job_metadata: JobMetadata) -> None:
        """Verify that search works for this Portkey config."""
        log.info(f"Config coverage: testing search '{search_combo.handle}'")
        model_deck = get_model_deck()
        inference_model = model_deck.get_required_inference_model(model_handle=search_combo.handle, model_type=ModelType.SEARCH)
        worker = SearchWorkerFactory.make_search_worker(inference_model=inference_model)
        search_setting = SearchSetting(
            model=search_combo.handle,
            max_results=2,
        )
        search_job = SearchJobFactory.make_search_job(
            query="What makes declarative languages different from imperative languages?",
            search_setting=search_setting,
            job_metadata=job_metadata,
        )
        result = await worker.search_sourced_answer(search_job=search_job)
        assert result.answer
        pretty_print(result, title=f"Search result for '{search_combo.handle}'")
