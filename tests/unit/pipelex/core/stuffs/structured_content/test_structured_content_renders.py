import pytest

from tests.unit.pipelex.core.stuffs.structured_content.test_data import SampleStructuredContent, TestData


@pytest.mark.asyncio(loop_scope="class")
class TestStructuredContentRenders:
    """Tests for StructuredContent render methods."""

    def test_rendered_markdown_minimal(self):
        """Verify rendered_markdown returns markdown-formatted content."""
        content = SampleStructuredContent(name=TestData.SAMPLE_NAME, value=TestData.SAMPLE_VALUE)
        result = content.rendered_markdown()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN_MINIMAL

    def test_rendered_markdown_full(self):
        """Verify rendered_markdown includes all populated fields."""
        content = SampleStructuredContent(
            name=TestData.SAMPLE_NAME,
            value=TestData.SAMPLE_VALUE,
            description=TestData.SAMPLE_DESCRIPTION,
        )
        result = content.rendered_markdown()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN_FULL

    def test_rendered_for_prompt(self):
        """Verify rendered_for_prompt returns markdown format."""
        content = SampleStructuredContent(name=TestData.SAMPLE_NAME, value=TestData.SAMPLE_VALUE)
        result = content.rendered_for_prompt()
        # rendered_for_prompt calls rendered_markdown
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN_MINIMAL

    def test_rendered_html_minimal(self):
        """Verify rendered_html returns HTML table format."""
        content = SampleStructuredContent(name=TestData.SAMPLE_NAME, value=TestData.SAMPLE_VALUE)
        result = content.rendered_html()
        assert result == TestData.EXPECTED_RENDERED_HTML_MINIMAL

    def test_rendered_html_full(self):
        """Verify rendered_html includes all populated fields."""
        content = SampleStructuredContent(
            name=TestData.SAMPLE_NAME,
            value=TestData.SAMPLE_VALUE,
            description=TestData.SAMPLE_DESCRIPTION,
        )
        result = content.rendered_html()
        assert result == TestData.EXPECTED_RENDERED_HTML_FULL

    async def test_rendered_markdown_async(self):
        """Verify async rendered_markdown returns the same as sync version."""
        content = SampleStructuredContent(name=TestData.SAMPLE_NAME, value=TestData.SAMPLE_VALUE)
        result = await content.rendered_markdown_async()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN_MINIMAL

    async def test_rendered_html_async(self):
        """Verify async rendered_html returns the same as sync version."""
        content = SampleStructuredContent(name=TestData.SAMPLE_NAME, value=TestData.SAMPLE_VALUE)
        result = await content.rendered_html_async()
        assert result == TestData.EXPECTED_RENDERED_HTML_MINIMAL
