import json
import re
from typing import Any

import pytest
from pytest import CaptureFixture

from pipelex.core.stuffs.json_content import JSONContent
from pipelex.tools.misc.pretty import pretty_print


def remove_ansi_escape_codes(text: str) -> str:
    """Remove ANSI color codes from terminal output."""
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)


@pytest.mark.asyncio(loop_scope="class")
class TestJSONContentRendering:
    """Test JSONContent rendering methods."""

    # rendered_plain() tests

    async def test_rendered_plain_simple(self):
        """Test plain rendering of simple JSON."""
        json_obj = {"name": "test", "value": 42}
        content = JSONContent(json_obj=json_obj)
        output = await content.rendered_plain_async()

        # Should be valid JSON
        parsed = json.loads(output)
        assert parsed == json_obj

        # Should be indented (4 spaces)
        assert "    " in output

    async def test_rendered_plain_nested(self):
        """Test plain rendering of nested JSON."""
        json_obj = {
            "user": {"name": "John", "age": 30},
            "active": True,
        }
        content = JSONContent(json_obj=json_obj)
        output = await content.rendered_plain_async()

        parsed = json.loads(output)
        assert parsed == json_obj
        assert "John" in output
        assert "30" in output

    async def test_rendered_plain_empty(self):
        """Test plain rendering of empty JSON."""
        json_obj: dict[str, Any] = {}
        content = JSONContent(json_obj=json_obj)
        output = await content.rendered_plain_async()

        assert output.strip() == "{}"

    # rendered_json() tests

    async def test_rendered_json_matches_plain(self):
        """Test that rendered_json produces same output as rendered_plain."""
        json_obj = {"name": "test", "value": 42, "nested": {"key": "value"}}
        content = JSONContent(json_obj=json_obj)

        json_output = await content.rendered_json_async()
        plain_output = await content.rendered_plain_async()

        assert json_output == plain_output

    async def test_rendered_json_valid_format(self):
        """Test that rendered_json produces valid JSON."""
        json_obj = {"items": [1, 2, 3], "metadata": {"count": 3}}
        content = JSONContent(json_obj=json_obj)
        output = await content.rendered_json_async()

        # Should be parseable
        parsed = json.loads(output)
        assert parsed == json_obj

    # rendered_markdown() tests

    async def test_rendered_markdown_simple(self):
        """Test markdown rendering of simple JSON."""
        json_obj = {"name": "test", "value": 42}
        content = JSONContent(json_obj=json_obj)
        output = await content.rendered_markdown_async()

        # Should contain key-value pairs
        assert "name" in output
        assert "test" in output
        assert "value" in output
        assert "42" in output

    async def test_rendered_markdown_with_level(self):
        """Test markdown rendering with custom heading level."""
        json_obj = {"title": "Test"}
        content = JSONContent(json_obj=json_obj)

        output_level1 = await content.rendered_markdown_async(level=1)
        output_level2 = await content.rendered_markdown_async(level=2)
        output_level3 = await content.rendered_markdown_async(level=3)

        # Different levels should produce different output
        # (exact format depends on convert_to_markdown implementation)
        assert output_level1 != output_level2
        assert output_level2 != output_level3

    async def test_rendered_markdown_nested(self):
        """Test markdown rendering of nested JSON."""
        json_obj = {
            "user": {"name": "John", "age": 30},
            "settings": {"theme": "dark"},
        }
        content = JSONContent(json_obj=json_obj)
        output = await content.rendered_markdown_async()

        # Should contain nested structure
        assert "user" in output
        assert "John" in output
        assert "settings" in output
        assert "dark" in output

    async def test_rendered_markdown_pretty_mode(self):
        """Test markdown rendering with pretty mode."""
        json_obj = {"name": "test", "value": 42}
        content = JSONContent(json_obj=json_obj)

        output_normal = await content.rendered_markdown_async(is_pretty=False)
        output_pretty = await content.rendered_markdown_async(is_pretty=True)

        # Both should contain the data (pretty mode may capitalize)
        assert "name" in output_normal.lower()
        assert "name" in output_pretty.lower()
        assert "test" in output_normal.lower()
        assert "test" in output_pretty.lower()

    # rendered_html() tests

    async def test_rendered_html_simple(self):
        """Test HTML rendering of simple JSON."""
        json_obj = {"name": "test", "value": 42}
        content = JSONContent(json_obj=json_obj)
        output = await content.rendered_html_async()

        # Should contain HTML table structure
        assert "<" in output  # HTML tags
        assert ">" in output
        # Should contain the data
        assert "name" in output or "test" in output

    async def test_rendered_html_nested(self):
        """Test HTML rendering of nested JSON."""
        json_obj = {
            "user": {"name": "John", "age": 30},
            "items": ["apple", "banana"],
        }
        content = JSONContent(json_obj=json_obj)
        output = await content.rendered_html_async()

        # Should contain HTML markup
        assert "<" in output
        assert ">" in output
        # Should contain the data
        assert "John" in output or "apple" in output

    async def test_rendered_html_empty(self):
        """Test HTML rendering of empty JSON."""
        json_obj: dict[str, Any] = {}
        content = JSONContent(json_obj=json_obj)
        output = await content.rendered_html_async()

        # Should still produce some HTML output
        # (exact format depends on json2html implementation)
        assert isinstance(output, str)

    # rendered_pretty() tests

    async def test_rendered_pretty_simple(self, capsys: CaptureFixture[str]):
        """Test pretty rendering of simple JSON."""
        json_obj = {"name": "test", "value": 42, "active": True}
        content = JSONContent(json_obj=json_obj)

        pretty_print(content.rendered_pretty(title="Simple JSON"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        # Should contain the data (Rich JSON doesn't use title parameter)
        assert "test" in output
        assert "42" in output
        assert "true" in output

    async def test_rendered_pretty_nested(self, capsys: CaptureFixture[str]):
        """Test pretty rendering of nested JSON."""
        json_obj = {
            "user": {"name": "Alice", "age": 25},
            "settings": {"theme": "light", "notifications": True},
        }
        content = JSONContent(json_obj=json_obj)

        pretty_print(content.rendered_pretty(title="Nested JSON"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        # Should contain the data
        assert "Alice" in output
        assert "theme" in output
        assert "light" in output

    async def test_rendered_pretty_with_arrays(self, capsys: CaptureFixture[str]):
        """Test pretty rendering of JSON with arrays."""
        json_obj = {
            "items": ["apple", "banana", "cherry"],
            "numbers": [1, 2, 3],
        }
        content = JSONContent(json_obj=json_obj)

        pretty_print(content.rendered_pretty(title="JSON with Arrays"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        # Should contain the array data
        assert "apple" in output
        assert "banana" in output
        assert "cherry" in output

    async def test_rendered_pretty_complex(self, capsys: CaptureFixture[str]):
        """Test pretty rendering of complex JSON structure."""
        json_obj = {
            "id": "abc123",
            "metadata": {
                "created": "2024-01-01",
                "tags": ["important", "urgent"],
            },
            "data": [
                {"name": "item1", "count": 10},
                {"name": "item2", "count": 20},
            ],
            "score": 95.5,
        }
        content = JSONContent(json_obj=json_obj)

        pretty_print(content.rendered_pretty(title="Complex JSON"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        # Should contain the complex data
        assert "abc123" in output
        assert "important" in output
        assert "item1" in output

    async def test_rendered_pretty_without_title(self, capsys: CaptureFixture[str]):
        """Test pretty rendering without a title."""
        json_obj = {"name": "test", "value": 42}
        content = JSONContent(json_obj=json_obj)

        pretty_print(content.rendered_pretty())

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        # Should still contain the data
        assert "test" in output
        assert "42" in output

    async def test_rendered_pretty_empty(self, capsys: CaptureFixture[str]):
        """Test pretty rendering of empty JSON."""
        json_obj: dict[str, Any] = {}
        content = JSONContent(json_obj=json_obj)

        pretty_print(content.rendered_pretty(title="Empty JSON"))

        captured = capsys.readouterr()
        output = remove_ansi_escape_codes(captured.out)

        # Should render empty object
        assert "{" in output
        assert "}" in output
