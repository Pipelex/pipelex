import pytest

from pipelex.core.stuffs.image_content import ImageContent
from tests.unit.pipelex.core.stuffs.image_content.test_data import TestData


class TestImageContentRenders:
    """Tests for ImageContent render methods."""

    def test_rendered_plain(self):
        """Verify rendered_plain returns the URL truncated to 500 chars."""
        content = ImageContent(url=TestData.SAMPLE_URL)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN

    def test_rendered_markdown(self):
        """Verify rendered_markdown returns markdown image format."""
        content = ImageContent(url=TestData.SAMPLE_URL)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN

    def test_rendered_html(self):
        """Verify rendered_html returns img tag with URL."""
        content = ImageContent(url=TestData.SAMPLE_URL)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML

    def test_rendered_html_with_public_url(self):
        """Verify rendered_html uses public_url when available."""
        content = ImageContent(url=TestData.SAMPLE_URL, public_url=TestData.SAMPLE_PUBLIC_URL)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML_WITH_DISPLAY_LINK

    def test_rendered_json(self):
        """Verify rendered_json returns JSON string with image_url and source_prompt."""
        content = ImageContent(url=TestData.SAMPLE_URL)
        assert content.rendered_json() == TestData.EXPECTED_RENDERED_JSON

    def test_rendered_json_with_prompt(self):
        """Verify rendered_json includes source_prompt when available."""
        content = ImageContent(url=TestData.SAMPLE_URL, source_prompt=TestData.SAMPLE_SOURCE_PROMPT)
        assert content.rendered_json() == TestData.EXPECTED_RENDERED_JSON_WITH_PROMPT

    def test_rendered_for_prompt(self):
        """Verify rendered_for_prompt returns markdown format."""
        content = ImageContent(url=TestData.SAMPLE_URL)
        assert content.rendered_for_prompt() == TestData.EXPECTED_RENDERED_FOR_PROMPT

    @pytest.mark.asyncio
    async def test_rendered_plain_async(self):
        """Verify async rendered_plain returns the same as sync version."""
        content = ImageContent(url=TestData.SAMPLE_URL)
        result = await content.rendered_plain_async()
        assert result == TestData.EXPECTED_RENDERED_PLAIN

    @pytest.mark.asyncio
    async def test_rendered_markdown_async(self):
        """Verify async rendered_markdown returns the same as sync version."""
        content = ImageContent(url=TestData.SAMPLE_URL)
        result = await content.rendered_markdown_async()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN

    @pytest.mark.asyncio
    async def test_rendered_html_async(self):
        """Verify async rendered_html returns the same as sync version."""
        content = ImageContent(url=TestData.SAMPLE_URL)
        result = await content.rendered_html_async()
        assert result == TestData.EXPECTED_RENDERED_HTML

    @pytest.mark.asyncio
    async def test_rendered_json_async(self):
        """Verify async rendered_json returns the same as sync version."""
        content = ImageContent(url=TestData.SAMPLE_URL)
        result = await content.rendered_json_async()
        assert result == content.rendered_json()
