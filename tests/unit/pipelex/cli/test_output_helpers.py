"""Unit tests for _output_helpers: build_run_output()."""

from __future__ import annotations

from typing import Any

from pipelex.cli.agent_cli.commands.run._output_helpers import build_run_output  # noqa: PLC2701


class TestBuildRunOutput:
    """Tests for build_run_output()."""

    def test_compact_with_result(self) -> None:
        """With with_memory=False and a compact_result, returns the compact dict directly."""
        compact: dict[str, Any] = {"clauses": [{"id": 1, "text": "clause one"}]}
        result = build_run_output(
            with_memory=False,
            main_stuff_json={"json": compact, "markdown": "# clause one"},
            working_memory_dump={"root": {}},
            compact_result=compact,
        )
        assert result == compact

    def test_compact_no_result(self) -> None:
        """With with_memory=False and compact_result=None, returns empty dict."""
        result = build_run_output(
            with_memory=False,
            main_stuff_json={},
            working_memory_dump={"root": {}},
            compact_result=None,
        )
        assert result == {}

    def test_full_with_memory(self) -> None:
        """With with_memory=True, returns main_stuff + working_memory envelope."""
        main_stuff: dict[str, Any] = {"json": {"key": "val"}, "markdown": "# val"}
        working_memory: dict[str, Any] = {"root": {"stuff_a": {"concept": "Text"}}}
        result = build_run_output(
            with_memory=True,
            main_stuff_json=main_stuff,
            working_memory_dump=working_memory,
            compact_result={"key": "val"},
        )
        assert result == {
            "main_stuff": main_stuff,
            "working_memory": working_memory,
        }

    def test_full_empty_main_stuff(self) -> None:
        """With with_memory=True and empty main_stuff_json, includes it as empty dict."""
        working_memory: dict[str, Any] = {"root": {}, "aliases": {}}
        result = build_run_output(
            with_memory=True,
            main_stuff_json={},
            working_memory_dump=working_memory,
            compact_result=None,
        )
        assert result == {
            "main_stuff": {},
            "working_memory": working_memory,
        }

    def test_with_memory_ignores_compact_result(self) -> None:
        """With with_memory=True, compact_result is ignored even if provided."""
        main_stuff: dict[str, Any] = {"json": {"a": 1}}
        working_memory: dict[str, Any] = {"root": {}}
        compact: dict[str, Any] = {"a": 1}
        result = build_run_output(
            with_memory=True,
            main_stuff_json=main_stuff,
            working_memory_dump=working_memory,
            compact_result=compact,
        )
        assert "main_stuff" in result
        assert "working_memory" in result
        assert result != compact

    def test_full_with_memory_includes_extra_metadata(self) -> None:
        """With with_memory=True and extra_metadata, metadata is merged into the envelope."""
        main_stuff: dict[str, Any] = {"json": {"key": "val"}, "markdown": "# val"}
        working_memory: dict[str, Any] = {"root": {"stuff_a": {"concept": "Text"}}}
        extra: dict[str, Any] = {"pipeline_run_id": "run-123", "pipeline_state": "COMPLETED"}
        result = build_run_output(
            with_memory=True,
            main_stuff_json=main_stuff,
            working_memory_dump=working_memory,
            compact_result={"key": "val"},
            extra_metadata=extra,
        )
        assert result["main_stuff"] == main_stuff
        assert result["working_memory"] == working_memory
        assert result["pipeline_run_id"] == "run-123"
        assert result["pipeline_state"] == "COMPLETED"

    def test_compact_ignores_extra_metadata(self) -> None:
        """With with_memory=False, extra_metadata is not included in compact output."""
        compact: dict[str, Any] = {"clauses": [{"id": 1}]}
        extra: dict[str, Any] = {"pipeline_run_id": "run-456", "pipeline_state": "COMPLETED"}
        result = build_run_output(
            with_memory=False,
            main_stuff_json={"json": compact},
            working_memory_dump={"root": {}},
            compact_result=compact,
            extra_metadata=extra,
        )
        assert result == compact
        assert "pipeline_run_id" not in result
