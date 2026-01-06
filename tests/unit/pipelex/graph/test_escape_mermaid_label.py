"""Unit tests for the escape_mermaid_label function."""

from pipelex.tools.mermaid.mermaid_utils import escape_mermaid_label


class TestEscapeMermaidLabel:
    """Tests for the escape_mermaid_label function."""

    def test_escape_quotes(self) -> None:
        """Test escaping double quotes."""
        result = escape_mermaid_label('Label with "quotes"')
        assert '"' not in result
        assert "'" in result

    def test_escape_brackets(self) -> None:
        """Test escaping square brackets."""
        result = escape_mermaid_label("Label [with] brackets")
        assert "[" not in result
        assert "]" not in result
        assert "(" in result
        assert ")" in result

    def test_no_escape_needed(self) -> None:
        """Test label that doesn't need escaping."""
        result = escape_mermaid_label("simple_label")
        assert result == "simple_label"
