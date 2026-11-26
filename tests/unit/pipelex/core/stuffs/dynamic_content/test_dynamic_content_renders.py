import pytest

from tests.unit.pipelex.core.stuffs.dynamic_content.cases import DynamicContentCases, SampleDynamicContent


class TestDynamicContentRenders:
    """Tests for DynamicContent render methods."""

    def test_rendered_markdown(self):
        """Verify rendered_markdown returns str(smart_dump())."""
        content = SampleDynamicContent(name=DynamicContentCases.SAMPLE_NAME, value=DynamicContentCases.SAMPLE_VALUE)
        result = content.rendered_markdown()
        assert result == DynamicContentCases.EXPECTED_RENDERED_MARKDOWN

    def test_rendered_html(self):
        """Verify rendered_html returns str(smart_dump())."""
        content = SampleDynamicContent(name=DynamicContentCases.SAMPLE_NAME, value=DynamicContentCases.SAMPLE_VALUE)
        result = content.rendered_html()
        assert result == DynamicContentCases.EXPECTED_RENDERED_HTML

    def test_rendered_for_prompt(self):
        """Verify rendered_for_prompt returns markdown format (str(smart_dump()))."""
        content = SampleDynamicContent(name=DynamicContentCases.SAMPLE_NAME, value=DynamicContentCases.SAMPLE_VALUE)
        result = content.rendered_for_prompt()
        assert result == DynamicContentCases.EXPECTED_RENDERED_FOR_PROMPT

    @pytest.mark.asyncio
    async def test_rendered_markdown_async(self):
        """Verify async rendered_markdown returns the same as sync version."""
        content = SampleDynamicContent(name=DynamicContentCases.SAMPLE_NAME, value=DynamicContentCases.SAMPLE_VALUE)
        result = await content.rendered_markdown_async()
        assert result == DynamicContentCases.EXPECTED_RENDERED_MARKDOWN

    @pytest.mark.asyncio
    async def test_rendered_html_async(self):
        """Verify async rendered_html returns the same as sync version."""
        content = SampleDynamicContent(name=DynamicContentCases.SAMPLE_NAME, value=DynamicContentCases.SAMPLE_VALUE)
        result = await content.rendered_html_async()
        assert result == DynamicContentCases.EXPECTED_RENDERED_HTML
