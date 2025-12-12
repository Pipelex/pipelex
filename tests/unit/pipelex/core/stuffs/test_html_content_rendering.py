import pytest

from pipelex.core.stuffs.stuff_content import StuffContent
from tests.unit.pipelex.core.stuffs.data import RenderedHtmlTestData


class TestRenderedHtml:
    """Test rendered_html() for HTML-like StuffContent implementations."""

    @pytest.mark.parametrize(("content", "expected"), RenderedHtmlTestData.RENDERED_HTML_TEST_CASES)
    def test_rendered_html(self, content: StuffContent, expected: str):
        rendered = content.rendered_html()

        assert rendered == expected
