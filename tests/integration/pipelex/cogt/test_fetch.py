import pytest

from pipelex import pretty_print
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.search.search_worker_factory import SearchWorkerFactory
from pipelex.hub import get_model_deck, get_report_delegate
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.cogt.test_data import FetchTestCases
from tests.integration.pipelex.fixtures.model_combo import ModelCombo


@pytest.mark.search
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestFetch:
    @pytest.mark.parametrize(
        ("topic", "url"),
        FetchTestCases.FETCH_URLS,
    )
    async def test_fetch_url(self, search_combo: ModelCombo, job_metadata: JobMetadata, topic: str, url: str) -> None:
        """Verify that fetch_url returns non-empty text content."""
        model_deck = get_model_deck()
        inference_model = model_deck.get_required_inference_model(model_handle=search_combo.handle, model_type=ModelType.SEARCH)
        worker = SearchWorkerFactory.make_fetch_worker(inference_model=inference_model)
        result = await worker.fetch_url(url=url, job_metadata=job_metadata)
        pretty_print(result, title=f"Fetch Result ({topic})")
        assert result.text is not None, "Expected non-empty text content"
        assert len(result.text.text) > 0, "Expected text to have content"
        assert result.raw_html is None, "Expected raw_html to be None when not requested"
        assert result.images is None, "Expected images to be None when not requested"
        get_report_delegate().generate_report()

    @pytest.mark.parametrize(
        ("topic", "url"),
        FetchTestCases.FETCH_URLS,
    )
    async def test_fetch_url_with_raw_html(self, search_combo: ModelCombo, job_metadata: JobMetadata, topic: str, url: str) -> None:
        """Verify that fetch_url returns raw HTML when requested."""
        model_deck = get_model_deck()
        inference_model = model_deck.get_required_inference_model(model_handle=search_combo.handle, model_type=ModelType.SEARCH)
        worker = SearchWorkerFactory.make_fetch_worker(inference_model=inference_model)
        result = await worker.fetch_url(url=url, job_metadata=job_metadata, include_raw_html=True)
        pretty_print(result, title=f"Fetch Result with HTML ({topic})")
        assert result.text is not None, "Expected non-empty text content"
        assert result.raw_html is not None, "Expected raw_html to be present when requested"
        assert len(result.raw_html) > 0, "Expected raw_html to have content"
        get_report_delegate().generate_report()

    @pytest.mark.parametrize(
        ("topic", "url"),
        FetchTestCases.FETCH_URLS,
    )
    async def test_fetch_url_with_images(self, search_combo: ModelCombo, job_metadata: JobMetadata, topic: str, url: str) -> None:
        """Verify that fetch_url returns images when requested."""
        model_deck = get_model_deck()
        inference_model = model_deck.get_required_inference_model(model_handle=search_combo.handle, model_type=ModelType.SEARCH)
        worker = SearchWorkerFactory.make_fetch_worker(inference_model=inference_model)
        result = await worker.fetch_url(url=url, job_metadata=job_metadata, extract_images=True)
        pretty_print(result, title=f"Fetch Result with Images ({topic})")
        assert result.text is not None, "Expected non-empty text content"
        assert result.images is not None, "Expected images to be present when requested"
        assert isinstance(result.images, list), "Expected images to be a list"
        assert len(result.images) > 0, "Expected images list to be non-empty"
        get_report_delegate().generate_report()
