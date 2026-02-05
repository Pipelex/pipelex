import pytest

from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from tests.unit.pipelex.core.stuffs.text_and_images_content.test_data import TestData


class TestTextAndImagesContentRenders:
    """Tests for TextAndImagesContent render methods."""

    def test_rendered_plain(self):
        """Verify rendered_plain returns the text content."""
        content = TextAndImagesContent(text=TestData.SAMPLE_TEXT, images=None)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN

    def test_rendered_plain_empty(self):
        """Verify rendered_plain handles empty text."""
        content = TextAndImagesContent(text=None, images=None)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN_EMPTY

    def test_rendered_markdown(self):
        """Verify rendered_markdown returns the text content."""
        content = TextAndImagesContent(text=TestData.SAMPLE_TEXT, images=None)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN

    def test_rendered_for_prompt(self):
        """Verify rendered_for_prompt returns markdown format."""
        content = TextAndImagesContent(text=TestData.SAMPLE_TEXT, images=None)
        assert content.rendered_for_prompt() == TestData.EXPECTED_RENDERED_FOR_PROMPT

    def test_rendered_html(self):
        """Verify rendered_html renders text content as HTML."""
        content = TextAndImagesContent(text=TestData.SAMPLE_TEXT, images=None)
        result = content.rendered_html()
        assert result == TestData.EXPECTED_RENDERED_HTML

    @pytest.mark.asyncio
    async def test_rendered_plain_async(self):
        """Verify async rendered_plain returns the same as sync version."""
        content = TextAndImagesContent(text=TestData.SAMPLE_TEXT, images=None)
        result = await content.rendered_plain_async()
        assert result == TestData.EXPECTED_RENDERED_PLAIN

    @pytest.mark.asyncio
    async def test_rendered_markdown_async(self):
        """Verify async rendered_markdown returns the same as sync version."""
        content = TextAndImagesContent(text=TestData.SAMPLE_TEXT, images=None)
        result = await content.rendered_markdown_async()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN

    @pytest.mark.asyncio
    async def test_rendered_html_async(self):
        """Verify async rendered_html returns the same as sync version."""
        content = TextAndImagesContent(text=TestData.SAMPLE_TEXT, images=None)
        result = await content.rendered_html_async()
        assert result == TestData.EXPECTED_RENDERED_HTML
