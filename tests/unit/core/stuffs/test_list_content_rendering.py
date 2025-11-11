import re

from pytest import CaptureFixture

from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.misc.pretty import MAX_RENDER_DEPTH, pretty_print


def remove_ansi_escape_codes(text: str) -> str:
    """Remove ANSI color codes from terminal output."""
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)


# Test Models


class SimpleData(StructuredContent):
    """Simple structured content for testing."""

    name: str
    value: int


class DeeplyNestedData(StructuredContent):
    """Deeply nested structure for depth limit testing."""

    level: int
    nested: "DeeplyNestedData | None" = None


class TestListContentRendering:
    """Test ListContent.rendered_pretty()"""

    def test_simple_list_content(self, capsys: CaptureFixture[str]):
        """Test rendering simple list of text content."""
        text_list = ListContent[TextContent](
            items=[
                TextContent(text="First item"),
                TextContent(text="Second item"),
                TextContent(text="Third item"),
            ]
        )
        pretty_print(text_list.rendered_pretty(title="Text List"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        assert "Text List" in output
        assert "First item" in output
        assert "Second item" in output
        assert "Third item" in output
        # Should show item numbers
        assert "1" in output
        assert "2" in output
        assert "3" in output

    def test_list_of_structured_content(self, capsys: CaptureFixture[str]):
        """Test rendering list of structured content."""
        data_list = ListContent[SimpleData](
            items=[
                SimpleData(name="alpha", value=1),
                SimpleData(name="beta", value=2),
                SimpleData(name="gamma", value=3),
            ]
        )
        pretty_print(data_list.rendered_pretty(title="Data List"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        assert "Data List" in output
        assert "alpha" in output
        assert "beta" in output
        assert "gamma" in output
        assert "1" in output
        assert "2" in output
        assert "3" in output

    def test_empty_list_content(self, capsys: CaptureFixture[str]):
        """Test rendering empty list."""
        empty_list = ListContent[TextContent](items=[])
        pretty_print(empty_list.rendered_pretty(title="Empty List"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        assert "Empty List" in output
        # Empty list should still render, just without items

    def test_list_content_depth_limit(self, capsys: CaptureFixture[str]):
        """Test that deeply nested lists fall back to JSON when depth exceeds limit."""
        # Create a deeply nested structure using DeeplyNestedData
        current = DeeplyNestedData(level=MAX_RENDER_DEPTH + 1, nested=None)
        for level in range(MAX_RENDER_DEPTH, 0, -1):
            current = DeeplyNestedData(level=level, nested=current)

        # Put it in a list and render at a depth that will trigger fallback
        deep_list = ListContent[DeeplyNestedData](items=[current])
        pretty_print(deep_list.rendered_pretty(title="Deep List", depth=MAX_RENDER_DEPTH - 1))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        assert "Deep List" in output
        # At max depth, inner items should fall back to JSON/Pretty rendering
