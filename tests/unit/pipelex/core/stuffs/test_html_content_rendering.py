import pytest

from pipelex.core.stuffs.stuff_content import StuffContent
from tests.unit.pipelex.core.stuffs.data import RenderedHtmlTestData


@pytest.mark.asyncio(loop_scope="class")
class TestRenderedHtml:
    """Test rendered_html() for HTML-like StuffContent implementations."""

    @pytest.mark.parametrize(("content", "expected"), RenderedHtmlTestData.RENDERED_HTML_TEST_CASES)
    async def test_rendered_html(self, content: StuffContent, expected: str):
        rendered = await content.rendered_html_async()

        assert rendered == expected
