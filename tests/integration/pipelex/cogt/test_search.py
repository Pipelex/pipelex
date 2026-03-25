import pytest
from pydantic import BaseModel

from pipelex import pretty_print
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.search.search_job_factory import SearchJobFactory
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.cogt.search.search_worker_factory import SearchWorkerFactory
from pipelex.hub import get_model_deck, get_report_delegate
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.cogt.test_data import SearchTestCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


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
    async def test_search_sourced_answer(self, search_combo: ModelCombo, job_metadata: JobMetadata, topic: str, query: str) -> None:
        """Verify that search_sourced_answer returns a non-empty answer with sources."""
        model_deck = get_model_deck()
        inference_model = model_deck.get_required_inference_model(model_handle=search_combo.handle, model_type=ModelType.SEARCH)
        worker = SearchWorkerFactory.make_search_worker(inference_model=inference_model)
        search_setting = SearchSetting(
            model=search_combo.handle,
            max_results=2,
        )
        search_job = SearchJobFactory.make_search_job(
            query=query,
            search_setting=search_setting,
            job_metadata=job_metadata,
        )
        result = await worker.search_sourced_answer(search_job=search_job)
        pretty_print(result, title=f"Sourced Answer Result ({topic})")
        assert result.answer, "Expected a non-empty answer"
        assert len(result.sources) > 0, "Expected at least one source"
        for source in result.sources:
            assert source.title, "Expected source to have a title"
            assert source.url, "Expected source to have a URL"
        get_report_delegate().generate_report()

    @pytest.mark.parametrize(
        ("topic", "query"),
        SearchTestCases.STRUCTURED_QUERIES,
    )
    async def test_search_structured(self, search_combo: ModelCombo, job_metadata: JobMetadata, topic: str, query: str) -> None:
        """Verify that search_structured returns a dict with the expected schema keys."""
        model_deck = get_model_deck()
        inference_model = model_deck.get_required_inference_model(model_handle=search_combo.handle, model_type=ModelType.SEARCH)
        worker = SearchWorkerFactory.make_search_worker(inference_model=inference_model)
        search_setting = SearchSetting(
            model=search_combo.handle,
        )
        search_job = SearchJobFactory.make_search_job(
            query=query,
            search_setting=search_setting,
            job_metadata=job_metadata,
        )
        result = await worker.search_structured(search_job=search_job, schema=TopicSummary)
        pretty_print(result, title=f"Structured Search Result ({topic})")
        assert isinstance(result, dict), "Expected a dict result"
        assert "data" in result, "Expected 'data' key in result"
        assert "sources" in result, "Expected 'sources' key in result"
        data = result["data"]
        assert "title" in data, "Expected 'title' key in data"
        assert "summary" in data, "Expected 'summary' key in data"
        assert "key_points" in data, "Expected 'key_points' key in data"
        assert len(result["sources"]) > 0, "Expected at least one source"
        get_report_delegate().generate_report()
