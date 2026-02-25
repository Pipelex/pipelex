import pytest

from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from tests.unit.pipelex.core.stuffs.page_content.test_data import TestData


class TestPageContentRenders:
    """Tests for PageContent render methods."""

    def test_rendered_markdown(self):
        """Verify rendered_markdown returns structured content."""
        text_and_images = TextAndImagesContent(
            text=TextContent(text="Page content text"),
            images=None,
        )
        content = PageContent(text_and_images=text_and_images, page_view=None)
        result = content.rendered_markdown()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN

    def test_rendered_for_prompt(self):
        """Verify rendered_for_prompt returns markdown format."""
        text_and_images = TextAndImagesContent(
            text=TextContent(text="Page content text"),
            images=None,
        )
        content = PageContent(text_and_images=text_and_images, page_view=None)
        result = content.rendered_for_prompt()
        assert result == TestData.EXPECTED_RENDERED_FOR_PROMPT

    def test_rendered_html(self):
        """Verify rendered_html returns HTML table format."""
        text_and_images = TextAndImagesContent(
            text=TextContent(text="Page content text"),
            images=None,
        )
        content = PageContent(text_and_images=text_and_images, page_view=None)
        result = content.rendered_html()
        assert result == TestData.EXPECTED_RENDERED_HTML

    @pytest.mark.asyncio
    async def test_rendered_markdown_async(self):
        """Verify async rendered_markdown returns the same as sync version."""
        text_and_images = TextAndImagesContent(
            text=TextContent(text="Page content text"),
            images=None,
        )
        content = PageContent(text_and_images=text_and_images, page_view=None)
        result = await content.rendered_markdown_async()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN

    @pytest.mark.asyncio
    async def test_rendered_html_async(self):
        """Verify async rendered_html returns the same as sync version."""
        text_and_images = TextAndImagesContent(
            text=TextContent(text="Page content text"),
            images=None,
        )
        content = PageContent(text_and_images=text_and_images, page_view=None)
        result = await content.rendered_html_async()
        assert result == TestData.EXPECTED_RENDERED_HTML
