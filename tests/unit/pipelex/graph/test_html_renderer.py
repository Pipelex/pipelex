"""Unit tests for the HTML renderer module."""

import re

import pytest

from pipelex.graph.csp import CSP_NONCE_SENTINEL
from pipelex.graph.mermaidflow.mermaid_html import render_mermaid_html
from pipelex.graph.mermaidflow.template_set import MERMAID_TEMPLATE_SET
from pipelex.tools.jinja2.jinja2_template_loader import TemplateLoader
from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry


class TestRenderMermaidHtml:
    """Tests for the render_mermaid_html function."""

    @pytest.fixture(autouse=True)
    def setup_templates(self) -> None:
        """Ensure Mermaid templates are loaded before tests."""
        TemplateRegistry.clear()
        TemplateLoader.reset()
        mermaid_name, mermaid_package, mermaid_templates = MERMAID_TEMPLATE_SET
        TemplateLoader.register_set(
            name=mermaid_name,
            package=mermaid_package,
            templates=mermaid_templates,
        )
        TemplateLoader.load(mermaid_name)

    SAMPLE_MERMAID_CODE = """flowchart TD
    n_abc123["generate_text"]
    n_def456["compose_output"]
    n_abc123 --> n_def456"""

    def test_html_contains_mermaid_code(self) -> None:
        """Test that the rendered HTML contains the Mermaid code.

        Note: The mermaid code is embedded as JSON, where '>' is Unicode-escaped
        for XSS protection. We check for node labels and IDs which are preserved.
        """
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)
        assert "generate_text" in result
        assert "compose_output" in result
        # Edge syntax is JSON-encoded: --> becomes --\u003e
        assert "n_abc123" in result
        assert "n_def456" in result

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

    def test_mermaid_code_preserved_in_json(self) -> None:
        """Test that Mermaid code is preserved correctly in JSON embedding.

        With autoescape=True, the mermaid code is embedded as JSON which
        properly escapes special characters for XSS protection while
        preserving the code for JavaScript parsing.
        """
        # Mermaid code with special characters
        mermaid_with_special = """flowchart TD
    n_a["Label with <angle> brackets"]
    n_b["Another & ampersand"]"""
        result = render_mermaid_html(mermaid_with_special)
        # The label text should be present (JSON-escaped but readable by JS)
        assert "Label with" in result
        assert "Another" in result
        # Verify JSON embedding is present
        assert 'type="application/json"' in result
        assert 'id="mermaid-code-data"' in result

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
        assert "<style" in result
        assert "</style>" in result

    def test_html_contains_csp_nonce_on_inline_script(self) -> None:
        """Verify the inline script tag has the CSP nonce sentinel."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)

        pattern = rf'<script nonce="{re.escape(CSP_NONCE_SENTINEL)}">'
        assert re.search(pattern, result), "Inline <script> should have the CSP nonce sentinel"

    def test_html_contains_csp_nonce_on_inline_style(self) -> None:
        """Verify the inline style tag has the CSP nonce sentinel."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)

        assert f'<style nonce="{CSP_NONCE_SENTINEL}">' in result

    def test_html_contains_csp_nonce_on_cdn_scripts(self) -> None:
        """Verify the CDN mermaid script tag has the CSP nonce sentinel."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)

        cdn_scripts = re.findall(r'<script [^>]*src="https?://[^"]*"[^>]*>', result)
        assert len(cdn_scripts) >= 1, "Expected at least 1 CDN script tag"
        for tag in cdn_scripts:
            assert f'nonce="{CSP_NONCE_SENTINEL}"' in tag, f"CDN script missing nonce: {tag}"

    def test_html_has_no_csp_meta_tag(self) -> None:
        """Verify no CSP meta tag is present (standalone HTML should be CSP-free)."""
        result = render_mermaid_html(self.SAMPLE_MERMAID_CODE)

        assert "Content-Security-Policy" not in result
