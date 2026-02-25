"""Tests for ListContent iterator protocol methods."""

from __future__ import annotations

import pytest

from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.text_content import TextContent


class TestListContentIteration:
    """Tests for ListContent iterator protocol enabling direct iteration."""

    def test_iter_basic(self) -> None:
        """Verify that direct iteration over ListContent yields items."""
        items = [
            TextContent(text="Item 1"),
            TextContent(text="Item 2"),
            TextContent(text="Item 3"),
        ]
        content: ListContent[TextContent] = ListContent(items=items)

        result = list(content)

        assert len(result) == 3
        assert result[0].text == "Item 1"
        assert result[1].text == "Item 2"
        assert result[2].text == "Item 3"

    def test_iter_empty(self) -> None:
        """Verify that iteration over empty ListContent yields nothing."""
        content: ListContent[TextContent] = ListContent(items=[])

        result = list(content)

        assert result == []

    def test_iter_in_for_loop(self) -> None:
        """Verify that ListContent works in a for loop."""
        items = [
            TextContent(text="A"),
            TextContent(text="B"),
        ]
        content: ListContent[TextContent] = ListContent(items=items)

        texts: list[str] = []
        for item in content:
            texts.append(item.text)

        assert texts == ["A", "B"]

    def test_len(self) -> None:
        """Verify that len(list_content) returns correct count."""
        items = [
            TextContent(text="Item 1"),
            TextContent(text="Item 2"),
            TextContent(text="Item 3"),
        ]
        content: ListContent[TextContent] = ListContent(items=items)

        assert len(content) == 3

    def test_len_empty(self) -> None:
        """Verify that len() works on empty list."""
        content: ListContent[TextContent] = ListContent(items=[])

        assert len(content) == 0

    def test_getitem_positive_index(self) -> None:
        """Verify that positive indexing works."""
        items = [
            TextContent(text="First"),
            TextContent(text="Second"),
            TextContent(text="Third"),
        ]
        content: ListContent[TextContent] = ListContent(items=items)

        assert content[0].text == "First"
        assert content[1].text == "Second"
        assert content[2].text == "Third"

    def test_getitem_negative_index(self) -> None:
        """Verify that negative indexing works."""
        items = [
            TextContent(text="First"),
            TextContent(text="Second"),
            TextContent(text="Third"),
        ]
        content: ListContent[TextContent] = ListContent(items=items)

        assert content[-1].text == "Third"
        assert content[-2].text == "Second"
        assert content[-3].text == "First"

    def test_getitem_slice(self) -> None:
        """Verify that slicing works."""
        items = [
            TextContent(text="A"),
            TextContent(text="B"),
            TextContent(text="C"),
            TextContent(text="D"),
        ]
        content: ListContent[TextContent] = ListContent(items=items)

        sliced = content[1:3]

        assert len(sliced) == 2
        assert sliced[0].text == "B"
        assert sliced[1].text == "C"

    def test_getitem_index_error(self) -> None:
        """Verify that IndexError is raised for out-of-bounds index."""
        items = [TextContent(text="Only one")]
        content: ListContent[TextContent] = ListContent(items=items)

        with pytest.raises(IndexError):
            _ = content[5]

    def test_contains_true(self) -> None:
        """Verify that 'in' operator returns True for items in the list."""
        item1 = TextContent(text="Item 1")
        item2 = TextContent(text="Item 2")
        content: ListContent[TextContent] = ListContent(items=[item1, item2])

        assert item1 in content
        assert item2 in content

    def test_contains_false(self) -> None:
        """Verify that 'in' operator returns False for items not in the list."""
        item1 = TextContent(text="Item 1")
        other_item = TextContent(text="Not in list")
        content: ListContent[TextContent] = ListContent(items=[item1])

        assert other_item not in content

    def test_multiple_iterations(self) -> None:
        """Verify that ListContent can be iterated multiple times."""
        items = [TextContent(text="A"), TextContent(text="B")]
        content: ListContent[TextContent] = ListContent(items=items)

        first_iter = [item.text for item in content]
        second_iter = [item.text for item in content]

        assert first_iter == second_iter == ["A", "B"]
