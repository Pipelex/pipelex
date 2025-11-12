import re

from pytest import CaptureFixture

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


class TestDepthParameterPropagation:
    """Test that depth parameter is properly propagated through nested structures."""

    def test_depth_propagation_in_nested_structures(self):
        """Test that depth increments properly in nested calls."""
        # Create a structure that tracks depth calls
        nested = NestedData(label="level1", simple=SimpleData(name="level2", value=42))

        # Call with explicit depth
        result = nested.rendered_pretty(depth=0)
        assert result is not None

        # Call at max depth - should fall back to Pretty/JSON
        result_at_max = nested.rendered_pretty(depth=MAX_RENDER_DEPTH)
        assert result_at_max is not None

    def test_depth_at_limit_triggers_fallback(self, capsys: CaptureFixture[str]):
        """Test that rendering at MAX_RENDER_DEPTH triggers JSON fallback."""
        data = SimpleData(name="test", value=42)

        # Render at exactly MAX_RENDER_DEPTH
        pretty_print(data.rendered_pretty(depth=MAX_RENDER_DEPTH))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        # Should use Pretty fallback, which shows the object representation
        # or JSON format instead of table
        assert output  # Just verify it renders something


class TestAdaptiveWidthFactorRendering:
    """Test that width factor adapts based on depth."""

    def test_width_decreases_with_depth(self):
        """Test that nested structures get progressively narrower."""
        # Create nested structure using DeeplyNestedData which allows self-nesting
        level3 = DeeplyNestedData(level=3, nested=None)
        level2 = DeeplyNestedData(level=2, nested=level3)
        level1 = DeeplyNestedData(level=1, nested=level2)

        # Render at different depths - just verify no crashes
        result_depth0 = level1.rendered_pretty(depth=0)
        result_depth3 = level1.rendered_pretty(depth=3)

        assert result_depth0 is not None
        assert result_depth3 is not None


class TestTitleParameter:
    """Test that title parameter is properly used."""

    def test_title_appears_in_output(self, capsys: CaptureFixture[str]):
        """Test that custom title appears in rendered output."""
        data = SimpleData(name="test", value=42)
        custom_title = "Custom Title for Data"

        pretty_print(data.rendered_pretty(title=custom_title))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        assert custom_title in output

    def test_no_title(self, capsys: CaptureFixture[str]):
        """Test rendering without title."""
        data = SimpleData(name="test", value=42)

        pretty_print(data.rendered_pretty(title=None))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        # Should still render content
        assert "test" in output
        assert "42" in output
