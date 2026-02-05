import pytest

from pipelex.core.stuffs.mermaid_content import MermaidContent
from tests.unit.pipelex.core.stuffs.mermaid_content.test_data import TestData


class TestMermaidContentRenders:
    """Tests for MermaidContent render methods."""

    def test_rendered_plain(self):
        """Verify rendered_plain returns the mermaid code."""
        content = MermaidContent(mermaid_code=TestData.SAMPLE_MERMAID_CODE, mermaid_url=TestData.SAMPLE_MERMAID_URL)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN

    def test_rendered_markdown(self):
        """Verify rendered_markdown returns the mermaid code."""
        content = MermaidContent(mermaid_code=TestData.SAMPLE_MERMAID_CODE, mermaid_url=TestData.SAMPLE_MERMAID_URL)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN

    def test_rendered_html(self):
        """Verify rendered_html returns mermaid div with escaped content."""
        content = MermaidContent(mermaid_code=TestData.SAMPLE_MERMAID_CODE, mermaid_url=TestData.SAMPLE_MERMAID_URL)
        assert content.rendered_html() == TestData.EXPECTED_RENDERED_HTML

    def test_rendered_json(self):
        """Verify rendered_json returns JSON string with mermaid key."""
        content = MermaidContent(mermaid_code=TestData.SAMPLE_MERMAID_CODE, mermaid_url=TestData.SAMPLE_MERMAID_URL)
        assert content.rendered_json() == TestData.EXPECTED_RENDERED_JSON

    def test_rendered_for_prompt(self):
        """Verify rendered_for_prompt returns the mermaid code."""
        content = MermaidContent(mermaid_code=TestData.SAMPLE_MERMAID_CODE, mermaid_url=TestData.SAMPLE_MERMAID_URL)
        assert content.rendered_for_prompt() == TestData.EXPECTED_RENDERED_FOR_PROMPT

    @pytest.mark.asyncio
    async def test_rendered_plain_async(self):
        """Verify async rendered_plain returns the same as sync version."""
        content = MermaidContent(mermaid_code=TestData.SAMPLE_MERMAID_CODE, mermaid_url=TestData.SAMPLE_MERMAID_URL)
        result = await content.rendered_plain_async()
        assert result == TestData.EXPECTED_RENDERED_PLAIN

    @pytest.mark.asyncio
    async def test_rendered_markdown_async(self):
        """Verify async rendered_markdown returns the same as sync version."""
        content = MermaidContent(mermaid_code=TestData.SAMPLE_MERMAID_CODE, mermaid_url=TestData.SAMPLE_MERMAID_URL)
        result = await content.rendered_markdown_async()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN

    @pytest.mark.asyncio
    async def test_rendered_html_async(self):
        """Verify async rendered_html returns the same as sync version."""
        content = MermaidContent(mermaid_code=TestData.SAMPLE_MERMAID_CODE, mermaid_url=TestData.SAMPLE_MERMAID_URL)
        result = await content.rendered_html_async()
        assert result == TestData.EXPECTED_RENDERED_HTML

    @pytest.mark.asyncio
    async def test_rendered_json_async(self):
        """Verify async rendered_json returns the same as sync version."""
        content = MermaidContent(mermaid_code=TestData.SAMPLE_MERMAID_CODE, mermaid_url=TestData.SAMPLE_MERMAID_URL)
        result = await content.rendered_json_async()
        assert result == TestData.EXPECTED_RENDERED_JSON
