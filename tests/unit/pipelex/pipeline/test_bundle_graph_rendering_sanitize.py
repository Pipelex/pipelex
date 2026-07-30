"""Unit tests for the bundle graph output-filename sanitizer."""

from __future__ import annotations

from pipelex.pipeline.bundle_graph_rendering import (
    _sanitize_graph_name,  # noqa: PLC2701 # pyright: ignore[reportPrivateUsage]
)


class TestSanitizeGraphName:
    """Tests for the _sanitize_graph_name helper that prevents path traversal."""

    def test_plain_filename(self) -> None:
        """A plain filename should pass through unchanged."""
        assert _sanitize_graph_name("dry_run.html") == "dry_run.html"

    def test_traversal_stripped(self) -> None:
        """Directory traversal components should be stripped."""
        assert _sanitize_graph_name("../../etc/passwd") == "passwd"

    def test_absolute_path_stripped(self) -> None:
        """Absolute paths should be reduced to just the filename."""
        assert _sanitize_graph_name("/var/data/evil.html") == "evil.html"

    def test_subdirectory_stripped(self) -> None:
        """Subdirectory paths should be reduced to just the filename."""
        assert _sanitize_graph_name("subdir/graph.html") == "graph.html"

    def test_empty_string_returns_default(self) -> None:
        """An empty string should return the default filename."""
        assert _sanitize_graph_name("") == "graph.html"
