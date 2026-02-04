from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.core.stuffs.list_content import ListContent
from tests.unit.pipelex.core.stuffs.list_content.test_data import TestData

if TYPE_CHECKING:
    from pipelex.core.stuffs.text_content import TextContent


class TestListContentRenders:
    """Tests for ListContent render methods."""

    def test_rendered_plain(self):
        """Verify rendered_plain returns bullet list format."""
        content: ListContent[TextContent] = ListContent(items=TestData.SAMPLE_TEXT_ITEMS)
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_PLAIN

    def test_rendered_markdown(self):
        """Verify rendered_markdown returns bullet list format."""
        content: ListContent[TextContent] = ListContent(items=TestData.SAMPLE_TEXT_ITEMS)
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_MARKDOWN

    def test_rendered_for_prompt(self):
        """Verify rendered_for_prompt returns bullet list format."""
        content: ListContent[TextContent] = ListContent(items=TestData.SAMPLE_TEXT_ITEMS)
        assert content.rendered_for_prompt() == TestData.EXPECTED_RENDERED_FOR_PROMPT

    def test_rendered_plain_empty(self):
        """Verify rendered_plain handles empty list."""
        content: ListContent[TextContent] = ListContent(items=[])
        assert content.rendered_plain() == TestData.EXPECTED_RENDERED_EMPTY

    def test_rendered_markdown_empty(self):
        """Verify rendered_markdown handles empty list."""
        content: ListContent[TextContent] = ListContent(items=[])
        assert content.rendered_markdown() == TestData.EXPECTED_RENDERED_EMPTY

    @pytest.mark.asyncio
    async def test_rendered_plain_async(self):
        """Verify async rendered_plain returns the same as sync version."""
        content: ListContent[TextContent] = ListContent(items=TestData.SAMPLE_TEXT_ITEMS)
        result = await content.rendered_plain_async()
        assert result == TestData.EXPECTED_RENDERED_PLAIN

    @pytest.mark.asyncio
    async def test_rendered_markdown_async(self):
        """Verify async rendered_markdown returns the same as sync version."""
        content: ListContent[TextContent] = ListContent(items=TestData.SAMPLE_TEXT_ITEMS)
        result = await content.rendered_markdown_async()
        assert result == TestData.EXPECTED_RENDERED_MARKDOWN
