import pytest

from pipelex.core.stuffs.json_content import JSONContent
from tests.unit.pipelex.core.stuffs.json_content.test_data import TestData


class TestJSONContentRenders:
    """Tests for JSONContent render methods."""

    def test_rendered_plain(self):
        """Verify rendered_plain returns formatted JSON string."""
        content = JSONContent(json_obj=TestData.SAMPLE_JSON_OBJ)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN

    def test_rendered_json(self):
        """Verify rendered_json returns formatted JSON string."""
        content = JSONContent(json_obj=TestData.SAMPLE_JSON_OBJ)
        assert content.rendered_json() == TestData.EXPECTED_RENDERED_JSON

    def test_rendered_markdown(self):
        """Verify rendered_markdown returns markdown-formatted list."""
        content = JSONContent(json_obj=TestData.SAMPLE_JSON_OBJ)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN

    def test_rendered_for_prompt(self):
        """Verify rendered_for_prompt returns JSON format for JSONContent."""
        content = JSONContent(json_obj=TestData.SAMPLE_JSON_OBJ)
        # JSONContent overrides rendered_for_prompt to return JSON format
        assert content.rendered_for_prompt() == TestData.EXPECTED_RENDERED_FOR_PROMPT

    @pytest.mark.asyncio
    async def test_rendered_plain_async(self):
        """Verify async rendered_plain returns the same as sync version."""
        content = JSONContent(json_obj=TestData.SAMPLE_JSON_OBJ)
        result = await content.rendered_plain_async()
        assert result == TestData.EXPECTED_RENDERED_PLAIN

    @pytest.mark.asyncio
    async def test_rendered_markdown_async(self):
        """Verify async rendered_markdown returns the same as sync version."""
        content = JSONContent(json_obj=TestData.SAMPLE_JSON_OBJ)
        result = await content.rendered_markdown_async()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN

    @pytest.mark.asyncio
    async def test_rendered_json_async(self):
        """Verify async rendered_json returns the same as sync version."""
        content = JSONContent(json_obj=TestData.SAMPLE_JSON_OBJ)
        result = await content.rendered_json_async()
        assert result == TestData.EXPECTED_RENDERED_JSON
