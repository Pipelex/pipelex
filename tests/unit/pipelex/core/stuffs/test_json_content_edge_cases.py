import json

import pytest

from pipelex.core.stuffs.json_content import JSONContent


@pytest.mark.asyncio(loop_scope="class")
class TestJSONContentEdgeCases:
    """Test edge cases for JSONContent."""

    async def test_json_with_unicode(self):
        """Test JSONContent with Unicode characters."""
        json_obj = {"message": "Hello 世界", "emoji": "🎉", "symbol": "€"}
        content = JSONContent(json_obj=json_obj)

        # Should handle Unicode in all rendering methods
        plain = await content.rendered_plain_async()
        assert "世界" in plain or "\\u" in plain  # Either literal or escaped

        markdown = await content.rendered_markdown_async()
        assert "message" in markdown

        html = await content.rendered_html_async()
        assert isinstance(html, str)

    async def test_json_with_special_characters(self):
        """Test JSONContent with special characters."""
        json_obj = {
            "quote": 'He said "hello"',
            "newline": "line1\nline2",
            "tab": "col1\tcol2",
        }
        content = JSONContent(json_obj=json_obj)

        plain = await content.rendered_plain_async()
        parsed = json.loads(plain)
        assert parsed == json_obj

    async def test_json_with_numbers(self):
        """Test JSONContent with various number types."""
        json_obj = {
            "integer": 42,
            "float": 3.14159,
            "negative": -10,
            "zero": 0,
            "scientific": 1.23e-4,
        }
        content = JSONContent(json_obj=json_obj)

        plain = await content.rendered_plain_async()
        parsed = json.loads(plain)
        assert parsed == json_obj

    async def test_json_with_boolean_and_null(self):
        """Test JSONContent with boolean and null values."""
        json_obj = {
            "is_active": True,
            "is_deleted": False,
            "data": None,
        }
        content = JSONContent(json_obj=json_obj)

        plain = await content.rendered_plain_async()
        parsed = json.loads(plain)
        assert parsed == json_obj
        assert parsed["is_active"] is True
        assert parsed["is_deleted"] is False
        assert parsed["data"] is None

    async def test_json_with_deeply_nested_structure(self):
        """Test JSONContent with deeply nested structure."""
        json_obj = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "level5": {"value": "deep"},
                        },
                    },
                },
            },
        }
        content = JSONContent(json_obj=json_obj)

        plain = await content.rendered_plain_async()
        parsed = json.loads(plain)
        assert parsed == json_obj
        assert parsed["level1"]["level2"]["level3"]["level4"]["level5"]["value"] == "deep"

    async def test_json_with_large_array(self):
        """Test JSONContent with a large array."""
        json_obj = {"numbers": list(range(100))}
        content = JSONContent(json_obj=json_obj)

        plain = await content.rendered_plain_async()
        parsed = json.loads(plain)
        assert parsed == json_obj
        assert len(parsed["numbers"]) == 100
