from pipelex.kit.markers import find_span, replace_span, wrap


class TestMarkers:
    """Test marker utilities for content insertion and replacement."""

    def test_find_span_with_markers(self):
        """Test finding span when markers exist."""
        text = "prefix\n<!-- BEGIN -->\ncontent\n<!-- END -->\nsuffix"
        span = find_span(text, "<!-- BEGIN -->", "<!-- END -->")
        assert span is not None
        assert text[span[0] : span[1]] == "<!-- BEGIN -->\ncontent\n<!-- END -->"

    def test_find_span_no_markers(self):
        """Test finding span when markers don't exist."""
        text = "no markers here"
        span = find_span(text, "<!-- BEGIN -->", "<!-- END -->")
        assert span is None

    def test_find_span_incomplete_markers(self):
        """Test finding span with only begin marker."""
        text = "prefix\n<!-- BEGIN -->\ncontent without end"
        span = find_span(text, "<!-- BEGIN -->", "<!-- END -->")
        assert span is None

    def test_wrap_content(self):
        """Test wrapping content with markers."""
        content = "line1\nline2"
        wrapped = wrap("<!-- BEGIN -->", "<!-- END -->", content)
        assert wrapped == "<!-- BEGIN -->\nline1\nline2\n<!-- END -->"

    def test_replace_span(self):
        """Test replacing content within a span."""
        text = "prefix\nOLD_CONTENT\nsuffix"
        span = (7, 18)  # Position of OLD_CONTENT
        new_text = replace_span(text, span, "NEW_CONTENT")
        assert new_text == "prefix\nNEW_CONTENT\nsuffix"
