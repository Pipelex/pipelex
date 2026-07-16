from typing import Any

import pytest

from pipelex.core.stuffs.html_rendering import render_value_html


class TestRenderValueHtml:
    """Plain strings must ALWAYS be escaped — a value that merely looks like HTML is untrusted input."""

    def test_html_looking_string_is_escaped(self):
        """A field value shaped like an HTML tag is an XSS vector and must not pass through raw."""
        result = render_value_html("<img src=x onerror=alert(1)>")
        assert result == "&lt;img src=x onerror=alert(1)&gt;"

    def test_plain_string_is_escaped(self):
        result = render_value_html("Tom & Jerry <3")
        assert result == "Tom &amp; Jerry &lt;3"

    def test_html_looking_string_inside_list_is_escaped(self):
        result = render_value_html(["<script>alert(1)</script>"])
        assert result == "<ul><li>&lt;script&gt;alert(1)&lt;/script&gt;</li></ul>"

    def test_html_looking_string_inside_dict_is_escaped(self):
        result = render_value_html({"payload": "<b>bold</b>"})
        assert result == "<dl><dt>payload</dt><dd>&lt;b&gt;bold&lt;/b&gt;</dd></dl>"

    def test_none_renders_as_em_none(self):
        """None is the only branch producing a literal HTML fragment with no data-derived value."""
        result = render_value_html(None)
        assert result == "<em>None</em>"

    @pytest.mark.parametrize(
        ("bool_value", "expected"),
        [
            (True, "True"),
            (False, "False"),
        ],
    )
    def test_bool_renders_as_true_false_not_int(self, bool_value: bool, expected: str):
        """Guards the bool-before-int match-arm ordering: bool is a subclass of int, so a reorder would render True as '1'."""
        result = render_value_html(bool_value)
        assert result == expected

    @pytest.mark.parametrize(
        "empty_container",
        [
            [],
            (),
            {},
        ],
    )
    def test_empty_containers_render_as_em_empty(self, empty_container: Any):
        result = render_value_html(empty_container)
        assert result == "<em>empty</em>"
