import pytest

from pipelex.core.stuffs.text_content import TextContent
from tests.unit.pipelex.core.stuffs.text_content.test_data import TestData


class TestTextContentRenders:
    """Tests for TextContent render methods."""

    def test_rendered_plain(self):
        """Verify rendered_plain returns the raw text."""
        content = TextContent(text=TestData.SAMPLE_TEXT)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN

    def test_rendered_markdown(self):
        """Verify rendered_markdown returns the raw text."""
        content = TextContent(text=TestData.SAMPLE_TEXT)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN

    def test_rendered_markdown_with_markdown_content(self):
        """Verify rendered_markdown preserves markdown formatting."""
        content = TextContent(text=TestData.SAMPLE_TEXT_WITH_MARKDOWN)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN_WITH_MD

    def test_rendered_html(self):
        """Verify rendered_html escapes HTML special characters."""
        content = TextContent(text=TestData.SAMPLE_TEXT)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML

    def test_rendered_html_escapes_special_characters(self):
        """Verify rendered_html properly escapes <, >, & characters."""
        content = TextContent(text=TestData.SAMPLE_TEXT_WITH_HTML_CHARS)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML_WITH_SPECIAL_CHARS

    def test_rendered_json(self):
        """Verify rendered_json returns JSON string with text key."""
        content = TextContent(text=TestData.SAMPLE_TEXT)
        assert content.rendered_json() == TestData.EXPECTED_RENDERED_JSON

    def test_rendered_for_prompt(self):
        """Verify rendered_for_prompt returns markdown format (which is plain text for TextContent)."""
        content = TextContent(text=TestData.SAMPLE_TEXT)
        assert content.rendered_for_prompt() == TestData.EXPECTED_RENDERED_FOR_PROMPT

    @pytest.mark.asyncio
    async def test_rendered_plain_async(self):
        """Verify async rendered_plain returns the same as sync version."""
        content = TextContent(text=TestData.SAMPLE_TEXT)
        result = await content.rendered_plain_async()
        assert result == TestData.EXPECTED_RENDERED_PLAIN

    @pytest.mark.asyncio
    async def test_rendered_markdown_async(self):
        """Verify async rendered_markdown returns the same as sync version."""
        content = TextContent(text=TestData.SAMPLE_TEXT)
        result = await content.rendered_markdown_async()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN

    @pytest.mark.asyncio
    async def test_rendered_html_async(self):
        """Verify async rendered_html returns the same as sync version."""
        content = TextContent(text=TestData.SAMPLE_TEXT)
        result = await content.rendered_html_async()
        assert result == TestData.EXPECTED_RENDERED_HTML

    @pytest.mark.asyncio
    async def test_rendered_json_async(self):
        """Verify async rendered_json returns the same as sync version."""
        content = TextContent(text=TestData.SAMPLE_TEXT)
        result = await content.rendered_json_async()
        assert result == TestData.EXPECTED_RENDERED_JSON
