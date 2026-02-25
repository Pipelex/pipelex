import pytest

from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent


class DataItem(StructuredContent):
    """Test structured content that uses level and is_pretty in markdown rendering."""

    user_name: str
    item_count: int


class TestListContentAsyncMarkdown:
    """Test that ListContent.rendered_markdown_async passes level and is_pretty parameters correctly."""

    @pytest.mark.asyncio(loop_scope="class")
    async def test_rendered_markdown_async_preserves_level_parameter(self):
        """Test that level parameter is passed to nested items in async rendering.

        The level parameter controls markdown heading depth (# vs ## vs ###).
        If level=2 is passed, nested item headings should start at ## not #.
        """
        list_content = ListContent[DataItem](
            items=[
                DataItem(user_name="Alice", item_count=10),
            ]
        )

        # Sync rendering with level=2
        sync_result = list_content.rendered_markdown(level=2, is_pretty=False)

        # Async rendering with level=2
        async_result = await list_content.rendered_markdown_async(level=2, is_pretty=False)

        # Both should produce identical output
        assert sync_result == async_result, (
            f"Sync and async rendered_markdown produce different output when level=2.\nSync result:\n{sync_result}\n\nAsync result:\n{async_result}"
        )

    @pytest.mark.asyncio(loop_scope="class")
    async def test_rendered_markdown_async_preserves_is_pretty_parameter(self):
        """Test that is_pretty parameter is passed to nested items in async rendering.

        The is_pretty parameter controls whether keys are prettified (snake_case -> Title Case).
        If is_pretty=True, keys like 'user_name' should become 'User Name'.
        """
        list_content = ListContent[DataItem](
            items=[
                DataItem(user_name="Bob", item_count=5),
            ]
        )

        # Sync rendering with is_pretty=True
        sync_result = list_content.rendered_markdown(level=1, is_pretty=True)

        # Async rendering with is_pretty=True
        async_result = await list_content.rendered_markdown_async(level=1, is_pretty=True)

        # Both should produce identical output
        assert sync_result == async_result, (
            f"Sync and async rendered_markdown produce different output when is_pretty=True.\n"
            f"Sync result:\n{sync_result}\n\n"
            f"Async result:\n{async_result}"
        )

    @pytest.mark.asyncio(loop_scope="class")
    async def test_rendered_markdown_async_with_both_parameters(self):
        """Test that both level and is_pretty parameters are passed correctly."""
        list_content = ListContent[DataItem](
            items=[
                DataItem(user_name="Charlie", item_count=15),
                DataItem(user_name="Diana", item_count=20),
            ]
        )

        # Sync rendering with custom parameters
        sync_result = list_content.rendered_markdown(level=3, is_pretty=True)

        # Async rendering with custom parameters
        async_result = await list_content.rendered_markdown_async(level=3, is_pretty=True)

        # Both should produce identical output
        assert sync_result == async_result, (
            f"Sync and async rendered_markdown produce different output with level=3, is_pretty=True.\n"
            f"Sync result:\n{sync_result}\n\n"
            f"Async result:\n{async_result}"
        )
