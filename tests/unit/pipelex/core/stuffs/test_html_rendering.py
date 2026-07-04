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
