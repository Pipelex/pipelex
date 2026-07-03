"""Unit tests for the plan trigger-diff: stored ack map vs current index map."""

from __future__ import annotations

from pipelex.cli.dev_cli.commands.drift.core import diff_trigger_files


class TestDriftCoreDiff:
    def test_added_removed_modified(self) -> None:
        stored = {
            "a.py": "blob:aaa",
            "b.py": "blob:bbb",
            "c.py": "blob:ccc",
        }
        current = {
            "b.py": "blob:bbb-changed",
            "c.py": "blob:ccc",
            "d.py": "blob:ddd",
        }
        diff = diff_trigger_files(stored, current=current)
        assert diff.added == ["d.py"]
        assert diff.removed == ["a.py"]
        assert diff.modified == ["b.py"]
        assert not diff.is_empty

    def test_identical_maps_yield_empty_diff(self) -> None:
        stored = {"a.py": "blob:aaa", "b.py": "blob:bbb"}
        diff = diff_trigger_files(stored, current=dict(stored))
        assert diff.added == []
        assert diff.removed == []
        assert diff.modified == []
        assert diff.is_empty

    def test_empty_stored_map_reports_everything_added(self) -> None:
        """With no previous ack, every current trigger file is 'added' — the initial-review case."""
        diff = diff_trigger_files({}, current={"a.py": "blob:aaa", "b.py": "blob:bbb"})
        assert diff.added == ["a.py", "b.py"]
        assert diff.removed == []
        assert diff.modified == []

    def test_diff_lists_are_sorted(self) -> None:
        stored = {"z.py": "blob:zzz", "m.py": "blob:mmm"}
        current = {"a.py": "blob:aaa", "b.py": "blob:bbb"}
        diff = diff_trigger_files(stored, current=current)
        assert diff.added == ["a.py", "b.py"]
        assert diff.removed == ["m.py", "z.py"]
