import pytest

from pipelex.core.stuffs.document_content import DocumentContent
from tests.unit.pipelex.core.stuffs.document_content.test_data import TestData


class TestDocumentContentRenders:
    """Tests for DocumentContent render methods."""

    def test_rendered_plain(self):
        """Verify rendered_plain returns the URL."""
        content = DocumentContent(url=TestData.SAMPLE_URL)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN

    def test_rendered_markdown(self):
        """Verify rendered_markdown returns markdown link format."""
        content = DocumentContent(url=TestData.SAMPLE_URL)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN

    def test_rendered_markdown_with_public_url(self):
        """Verify rendered_markdown uses public_url when available."""
        content = DocumentContent(url=TestData.SAMPLE_URL, public_url=TestData.SAMPLE_PUBLIC_URL)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN_WITH_DISPLAY_LINK

    def test_rendered_html(self):
        """Verify rendered_html returns anchor tag."""
        content = DocumentContent(url=TestData.SAMPLE_URL)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML

    def test_rendered_html_with_public_url(self):
        """Verify rendered_html uses public_url when available."""
        content = DocumentContent(url=TestData.SAMPLE_URL, public_url=TestData.SAMPLE_PUBLIC_URL)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML_WITH_PUBLIC_URL

    def test_rendered_for_prompt(self):
        """Verify rendered_for_prompt returns markdown format."""
        content = DocumentContent(url=TestData.SAMPLE_URL)
        assert content.rendered_for_prompt() == TestData.EXPECTED_RENDERED_FOR_PROMPT

    @pytest.mark.asyncio
    async def test_rendered_plain_async(self):
        """Verify async rendered_plain returns the same as sync version."""
        content = DocumentContent(url=TestData.SAMPLE_URL)
        result = await content.rendered_plain_async()
        assert result == TestData.EXPECTED_RENDERED_PLAIN

    @pytest.mark.asyncio
    async def test_rendered_markdown_async(self):
        """Verify async rendered_markdown returns the same as sync version."""
        content = DocumentContent(url=TestData.SAMPLE_URL)
        result = await content.rendered_markdown_async()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN

    @pytest.mark.asyncio
    async def test_rendered_html_async(self):
        """Verify async rendered_html returns the same as sync version."""
        content = DocumentContent(url=TestData.SAMPLE_URL)
        result = await content.rendered_html_async()
        assert result == TestData.EXPECTED_RENDERED_HTML

    @pytest.mark.asyncio
    async def test_rendered_json_async(self):
        """Verify async rendered_json returns the same as sync version."""
        content = DocumentContent(url=TestData.SAMPLE_URL)
        result = await content.rendered_json_async()
        # DocumentContent doesn't override rendered_json, so it uses base class behavior
        assert isinstance(result, str)
