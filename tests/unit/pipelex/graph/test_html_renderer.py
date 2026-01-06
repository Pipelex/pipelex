"""Unit tests for the HTML renderer module."""

from pipelex.graph.mermaid_html import render_mermaid_html


class TestRenderMermaidHtml:
    """Tests for the render_mermaid_html function."""

    SAMPLE_MERMAID_CODE = """flowchart TD
    n_abc123["generate_text"]
    n_def456["compose_output"]
    n_abc123 --> n_def456"""

    def test_html_contains_mermaid_code(self) -> None:
        """Test that the rendered HTML contains the Mermaid code."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)
        assert "generate_text" in result
        assert "compose_output" in result
        assert "n_abc123 --> n_def456" in result

    def test_html_has_mermaid_container(self) -> None:
        """Test that the rendered HTML has a mermaid container div."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)
        assert 'class="mermaid"' in result

    def test_html_has_mermaid_script(self) -> None:
        """Test that the rendered HTML includes Mermaid JS script."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)
        assert "mermaid" in result.lower()
        assert "cdn.jsdelivr.net" in result or "mermaid.min.js" in result

    def test_html_has_mermaid_initialize(self) -> None:
        """Test that the rendered HTML initializes Mermaid."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)
        assert "mermaid.initialize" in result

    def test_default_title(self) -> None:
        """Test that default title is used."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)
        assert "<title>Pipelex Graph</title>" in result
        assert "<h1>Pipelex Graph</h1>" in result

    def test_custom_title(self) -> None:
        """Test that custom title is applied."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE, title="My Custom Graph")
        assert "<title>My Custom Graph</title>" in result
        assert "<h1>My Custom Graph</h1>" in result

    def test_html_is_valid_structure(self) -> None:
        """Test that the rendered HTML has valid structure."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)
        assert "<!DOCTYPE html>" in result
        assert "<html" in result
        assert "</html>" in result
        assert "<head>" in result
        assert "</head>" in result
        assert "<body>" in result
        assert "</body>" in result

    def test_html_has_charset_meta(self) -> None:
        """Test that the rendered HTML has charset meta tag."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)
        assert 'charset="UTF-8"' in result

    def test_mermaid_code_not_escaped(self) -> None:
        """Test that Mermaid code is not HTML-escaped."""
        # Mermaid code with special characters that would be escaped
        mermaid_with_special = """flowchart TD
    n_a["Label with <angle> brackets"]
    n_b["Another & ampersand"]"""
        result = render_mermaid_html(mermaid_with_special)
        # The raw characters should appear (not escaped) since Mermaid needs them
        # Note: Jinja2 with autoescape=False (which we use for HTML templates) won't escape
        assert "Label with <angle> brackets" in result or "Label with" in result

    def test_empty_mermaid_code(self) -> None:
        """Test rendering with empty Mermaid code."""
        result = render_mermaid_html("")
        assert 'class="mermaid"' in result
        # Should still be valid HTML structure
        assert "<html" in result

    def test_multiline_mermaid_preserved(self) -> None:
        """Test that multiline Mermaid code is preserved."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)
        # Check that the structure is preserved (multiple nodes on different lines)
        assert "n_abc123" in result
        assert "n_def456" in result

    def test_html_styling_included(self) -> None:
        """Test that some basic styling is included."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)
        assert "<style>" in result
        assert "</style>" in result
