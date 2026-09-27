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
        """Square brackets become Mermaid entity codes, which render as the brackets themselves."""
        result = escape_mermaid_label("Label [with] brackets")
        assert result == "Label #91;with#93; brackets"

    def test_multiplicity_marker_survives(self) -> None:
        """A multiplicity marker keeps its brackets once rendered, rather than turning into `Record()`."""
        assert escape_mermaid_label("Record[]") == "Record#91;#93;"
        assert escape_mermaid_label("Record[3]") == "Record#91;3#93;"

    def test_no_escape_needed(self) -> None:
        """Test label that doesn't need escaping."""
        result = escape_mermaid_label("simple_label")
        assert result == "simple_label"
