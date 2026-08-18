"""Unit tests for pruning: dropping map entries whose test *file* no longer exists.

The criterion is the filesystem and never the collected set, which is what makes the pruning safe to
run under a marker-filtered collection — and what makes `tests/unit/repo/test_test_durations_paths.py`
self-healing, since `--store-durations` only ever merges and would otherwise keep the corpse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.cli.dev_cli.commands.duration_map import prune_dead_paths

if TYPE_CHECKING:
    from pathlib import Path


class TestDurationMapPruning:
    def test_drops_entries_whose_test_file_is_gone(self, tmp_path: Path) -> None:
        (tmp_path / "live.py").write_text("", encoding="utf-8")
        kept, dropped = prune_dead_paths(durations={"live.py::t": 1.0, "gone.py::t": 2.0}, repo_root=tmp_path)
        assert kept == {"live.py::t": 1.0}
        assert dropped == ["gone.py::t"]

    def test_keeps_a_live_file_whose_tests_are_marker_excluded(self, tmp_path: Path) -> None:
        """Pruning is a filesystem check precisely so it cannot delete tests a marker filter hid."""
        (tmp_path / "e2e.py").write_text("", encoding="utf-8")
        kept, dropped = prune_dead_paths(durations={"e2e.py::t": 3.0}, repo_root=tmp_path)
        assert kept == {"e2e.py::t": 3.0}
        assert not dropped

    def test_is_a_no_op_when_every_path_exists(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("", encoding="utf-8")
        durations = {"a.py::t1": 1.0, "a.py::t2": 2.0}
        kept, dropped = prune_dead_paths(durations=durations, repo_root=tmp_path)
        assert kept == durations
        assert not dropped
