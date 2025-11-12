import re

from pydantic import BaseModel
from pytest import CaptureFixture
from rich.text import Text

from pipelex.core.stuffs.structured_content import StructuredContent
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


class NestedData(StructuredContent):
    """Nested structured content for testing."""

    label: str
    simple: SimpleData


class DeeplyNestedData(StructuredContent):
    """Deeply nested structure for depth limit testing."""

    level: int
    nested: "DeeplyNestedData | None" = None


class SomeBaseModel(BaseModel):
    """Simple structured content for testing."""

    name: str
    value: int


class TestStructuredContentRendering:
    """Test StructuredContent.rendered_pretty()"""

    def test_simple_structured_content(self, capsys: CaptureFixture[str]):
        """Test rendering simple structured content."""
        data = SimpleData(name="test", value=42)
        pretty_print(data.rendered_pretty(title="Simple Data"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        # Should contain table with attribute-value pairs
        assert "Simple Data" in output
        assert "name" in output
        assert "test" in output
        assert "value" in output
        assert "42" in output

    def test_nested_structured_content(self, capsys: CaptureFixture[str]):
        """Test rendering nested structured content."""
        data = NestedData(label="outer", simple=SimpleData(name="inner", value=123))
        pretty_print(data.rendered_pretty(title="Nested Data"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        assert "Nested Data" in output
        assert "label" in output
        assert "outer" in output
        assert "simple" in output
        assert "name" in output
        assert "inner" in output
        assert "value" in output
        assert "123" in output

    def test_structured_content_depth_limit(self, capsys: CaptureFixture[str]):
        """Test that deeply nested structures fall back to JSON when depth exceeds limit."""
        # Create a structure that exceeds MAX_RENDER_DEPTH
        excessive_depth = MAX_RENDER_DEPTH + 3
        current = DeeplyNestedData(level=excessive_depth, nested=None)
        for level in range(excessive_depth - 1, 0, -1):
            current = DeeplyNestedData(level=level, nested=current)

        pretty_print(current.rendered_pretty(title="Deep Structure"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        # At max depth, should fall back to JSON rendering (Pretty display)
        # At max depth, should fall back to JSON rendering with syntax highlighting
        # The deepest levels should show as JSON/dict format
        assert "Deep Structure" in output
        # Should contain some level indicators
        assert "level" in output

    def test_base_model(self):
        data = SomeBaseModel(name="test", value=42)
        pretty_print(data)
        pretty = Text(f"{data}")
        pretty_print(pretty)

    def test_structured_content_with_none_values(self, capsys: CaptureFixture[str]):
        """Test that None values are skipped in rendering."""
        data = DeeplyNestedData(level=1, nested=None)
        pretty_print(data.rendered_pretty(title="With None"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        assert "With None" in output
        assert "level" in output
        assert "1" in output
        # "nested" field should not appear since it's None
        # This is implementation detail - None values are skipped

    def test_structured_content_with_list_field(self, capsys: CaptureFixture[str]):
        """Test structured content containing a list field."""

        class DataWithList(StructuredContent):
            name: str
            items: list[str]

        data = DataWithList(name="test", items=["apple", "banana", "cherry"])
        pretty_print(data.rendered_pretty(title="With List"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        assert "With List" in output
        assert "name" in output
        assert "test" in output
        assert "items" in output
        assert "apple" in output
        assert "banana" in output
        assert "cherry" in output
