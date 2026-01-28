import pytest

from pipelex.core.stuffs.html_content import HtmlContent
from tests.unit.pipelex.core.stuffs.html_content.test_data import TestData


class TestHtmlContentRenders:
    """Tests for HtmlContent render methods."""

    def test_rendered_plain(self):
        """Verify rendered_plain returns the inner_html."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN

    def test_rendered_markdown(self):
        """Verify rendered_markdown returns the inner_html."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN

    def test_rendered_html(self):
        """Verify rendered_html wraps content in div with escaped css_class."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML

    def test_rendered_html_escapes_css_class(self):
        """Verify rendered_html properly escapes potentially dangerous css_class values."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.XSS_CSS_CLASS)
        assert content.rendered_html() == TestData.EXPECTED_XSS_PROTECTED_HTML

    def test_rendered_json(self):
        """Verify rendered_json returns JSON string with html and css_class keys."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        assert content.rendered_json() == TestData.EXPECTED_RENDERED_JSON

    def test_rendered_for_prompt(self):
        """Verify rendered_for_prompt returns markdown format (which is inner_html for HtmlContent)."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        assert content.rendered_for_prompt() == TestData.EXPECTED_RENDERED_FOR_PROMPT

    @pytest.mark.asyncio
    async def test_rendered_plain_async(self):
        """Verify async rendered_plain returns the same as sync version."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        result = await content.rendered_plain_async()
        assert result == TestData.EXPECTED_RENDERED_PLAIN

    @pytest.mark.asyncio
    async def test_rendered_markdown_async(self):
        """Verify async rendered_markdown returns the same as sync version."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        result = await content.rendered_markdown_async()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN

    @pytest.mark.asyncio
    async def test_rendered_html_async(self):
        """Verify async rendered_html returns the same as sync version."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        result = await content.rendered_html_async()
        assert result == TestData.EXPECTED_RENDERED_HTML

    @pytest.mark.asyncio
    async def test_rendered_json_async(self):
        """Verify async rendered_json returns the same as sync version."""
        content = HtmlContent(inner_html=TestData.SAMPLE_INNER_HTML, css_class=TestData.SAMPLE_CSS_CLASS)
        result = await content.rendered_json_async()
        assert result == TestData.EXPECTED_RENDERED_JSON
