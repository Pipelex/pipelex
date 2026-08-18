"""Unit tests for reading and writing the committed `.test_durations` file.

The on-disk shape is pytest-split's own, so the plugin and this refresh stay interchangeable readers
of the same artifact.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pipelex.cli.dev_cli.commands.duration_map import load_duration_map, write_duration_map

if TYPE_CHECKING:
    from pathlib import Path


class TestDurationMapIo:
    def test_absent_file_reads_as_an_empty_map(self, tmp_path: Path) -> None:
        """A first-ever run has no file, and must mean 'nothing covered' rather than crash."""
        assert load_duration_map(path=tmp_path / "nope") == {}

    def test_round_trips_through_disk(self, tmp_path: Path) -> None:
        path = tmp_path / ".test_durations"
        durations = {"b.py::t": 2.0, "a.py::t": 1.0}
        write_duration_map(path=path, durations=durations)
        assert load_duration_map(path=path) == durations

    def test_written_file_is_sorted_and_newline_terminated(self, tmp_path: Path) -> None:
        """Sorted keys keep the diff line-local; the trailing newline keeps git quiet."""
        path = tmp_path / ".test_durations"
        write_duration_map(path=path, durations={"b.py::t": 2.0, "a.py::t": 1.0})
        body = path.read_text(encoding="utf-8")
        assert body.endswith("}\n")
        assert list(json.loads(body)) == ["a.py::t", "b.py::t"]

    def test_reads_the_pre_v1_list_of_lists_format(self, tmp_path: Path) -> None:
        """pytest-split still accepts it, so a map written by an old plugin must not crash the refresh."""
        path = tmp_path / ".test_durations"
        path.write_text(json.dumps([["a.py::t", 1.0]]), encoding="utf-8")
        assert load_duration_map(path=path) == {"a.py::t": 1.0}
