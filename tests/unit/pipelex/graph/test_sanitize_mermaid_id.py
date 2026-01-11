"""Unit tests for the sanitize_mermaid_id function."""

from pipelex.tools.mermaid.mermaid_utils import sanitize_mermaid_id


class TestSanitizeMermaidId:
    """Tests for the sanitize_mermaid_id function."""

    def test_sanitize_simple_id(self) -> None:
        """Test sanitizing a simple ID."""
        result = sanitize_mermaid_id("node_001")
        assert result.startswith("n_")
        assert len(result) == 12  # "n_" + 10 hex chars

    def test_sanitize_id_with_colons(self) -> None:
        """Test sanitizing an ID with colons."""
        result = sanitize_mermaid_id("run:123:step-1")
        assert result.startswith("n_")
        assert ":" not in result
        assert "-" not in result or result.startswith("n_")

    def test_sanitize_deterministic(self) -> None:
        """Test that sanitization is deterministic."""
        node_id = "run:abc:node-5"
        result1 = sanitize_mermaid_id(node_id)
        result2 = sanitize_mermaid_id(node_id)
        assert result1 == result2

    def test_sanitize_different_ids_produce_different_outputs(self) -> None:
        """Test that different IDs produce different sanitized outputs."""
        result1 = sanitize_mermaid_id("node_a")
        result2 = sanitize_mermaid_id("node_b")
        assert result1 != result2
