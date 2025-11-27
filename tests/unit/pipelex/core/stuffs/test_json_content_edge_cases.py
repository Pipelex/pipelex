import json
import math

from pipelex.core.stuffs.json_content import JSONContent


class TestJSONContentEdgeCases:
    """Test edge cases for JSONContent."""

    def test_json_with_unicode(self):
        """Test JSONContent with Unicode characters."""
        json_obj = {"message": "Hello 世界", "emoji": "🎉", "symbol": "€"}
        content = JSONContent(json_obj=json_obj)

        # Should handle Unicode in all rendering methods
        plain = content.rendered_plain()
        assert "世界" in plain or "\\u" in plain  # Either literal or escaped

        markdown = content.rendered_markdown()
        assert "message" in markdown

        html = content.rendered_html()
        assert isinstance(html, str)

    def test_json_with_special_characters(self):
        """Test JSONContent with special characters."""
        json_obj = {
            "quote": 'He said "hello"',
            "newline": "line1\nline2",
            "tab": "col1\tcol2",
        }
        content = JSONContent(json_obj=json_obj)

        plain = content.rendered_plain()
        parsed = json.loads(plain)
        assert parsed == json_obj

    def test_json_with_numbers(self):
        """Test JSONContent with various number types."""
        json_obj = {
            "integer": 42,
            "float": math.pi,
            "negative": -10,
            "zero": 0,
            "scientific": 1.23e-4,
        }
        content = JSONContent(json_obj=json_obj)

        plain = content.rendered_plain()
        parsed = json.loads(plain)
        assert parsed == json_obj

    def test_json_with_boolean_and_null(self):
        """Test JSONContent with boolean and null values."""
        json_obj = {
            "is_active": True,
            "is_deleted": False,
            "data": None,
        }
        content = JSONContent(json_obj=json_obj)

        plain = content.rendered_plain()
        parsed = json.loads(plain)
        assert parsed == json_obj
        assert parsed["is_active"] is True
        assert parsed["is_deleted"] is False
        assert parsed["data"] is None

    def test_json_with_deeply_nested_structure(self):
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

        plain = content.rendered_plain()
        parsed = json.loads(plain)
        assert parsed == json_obj
        assert parsed["level1"]["level2"]["level3"]["level4"]["level5"]["value"] == "deep"

    def test_json_with_large_array(self):
        """Test JSONContent with a large array."""
        json_obj = {"numbers": list(range(100))}
        content = JSONContent(json_obj=json_obj)

        plain = content.rendered_plain()
        parsed = json.loads(plain)
        assert parsed == json_obj
        assert len(parsed["numbers"]) == 100
