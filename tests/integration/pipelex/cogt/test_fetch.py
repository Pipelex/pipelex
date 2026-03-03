import pytest

from pipelex import pretty_print
from pipelex.cogt.search.search_worker_factory import get_fetch_worker
from tests.integration.pipelex.cogt.test_data import FetchTestCases


@pytest.mark.search
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestFetch:
    @pytest.mark.parametrize(
        ("topic", "url"),
        FetchTestCases.FETCH_URLS,
    )
    async def test_fetch_url(self, topic: str, url: str) -> None:
        """Verify that fetch_url returns non-empty text content."""
        worker = get_fetch_worker("linkup")
        result = await worker.fetch_url(url=url)
        pretty_print(result, title=f"Fetch Result ({topic})")
        assert result.text is not None, "Expected non-empty text content"
        assert len(result.text.text) > 0, "Expected text to have content"
        assert result.raw_html is None, "Expected raw_html to be None when not requested"
        assert result.images is None, "Expected images to be None when not requested"

    @pytest.mark.parametrize(
        ("topic", "url"),
        FetchTestCases.FETCH_URLS,
    )
    async def test_fetch_url_with_raw_html(self, topic: str, url: str) -> None:
        """Verify that fetch_url returns raw HTML when requested."""
        worker = get_fetch_worker("linkup")
        result = await worker.fetch_url(url=url, include_raw_html=True)
        pretty_print(result, title=f"Fetch Result with HTML ({topic})")
        assert result.text is not None, "Expected non-empty text content"
        assert result.raw_html is not None, "Expected raw_html to be present when requested"
        assert len(result.raw_html) > 0, "Expected raw_html to have content"

    @pytest.mark.parametrize(
        ("topic", "url"),
        FetchTestCases.FETCH_URLS,
    )
    async def test_fetch_url_with_images(self, topic: str, url: str) -> None:
        """Verify that fetch_url returns images when requested."""
        worker = get_fetch_worker("linkup")
        result = await worker.fetch_url(url=url, extract_images=True)
        pretty_print(result, title=f"Fetch Result with Images ({topic})")
        assert result.text is not None, "Expected non-empty text content"
        assert result.images is not None, "Expected images to be present when requested"
        assert isinstance(result.images, list), "Expected images to be a list"
