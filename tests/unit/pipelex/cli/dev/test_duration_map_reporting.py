"""Unit tests for the refresh's change accounting — what the command reports it did to the file."""

from __future__ import annotations

from pipelex.cli.dev_cli.commands.duration_map import count_changes


class TestDurationMapReporting:
    def test_a_new_entry_counts_as_added_and_not_as_rewritten(self) -> None:
        """The two figures are disjoint: an entry with no previous value was not *re*-written.

        Counting a new id as rewritten too made a first-ever refresh report the whole map twice.
        """
        added, rewritten = count_changes(previous={}, stabilized={"a.py::t": 1.0, "b.py::t": 2.0})
        assert added == 2
        assert rewritten == 0

    def test_a_moved_entry_counts_as_rewritten_and_not_as_added(self) -> None:
        added, rewritten = count_changes(previous={"a.py::t": 1.0}, stabilized={"a.py::t": 9.0})
        assert added == 0
        assert rewritten == 1

    def test_an_unchanged_entry_counts_as_neither(self) -> None:
        """A value kept by `stabilize` produces no diff line, so it must show up in neither figure."""
        added, rewritten = count_changes(previous={"a.py::t": 1.0}, stabilized={"a.py::t": 1.0})
        assert added == 0
        assert rewritten == 0

    def test_counts_a_mixed_refresh_the_way_the_diff_reads(self) -> None:
        added, rewritten = count_changes(
            previous={"kept.py::t": 1.0, "moved.py::t": 1.0, "gone.py::t": 1.0},
            stabilized={"kept.py::t": 1.0, "moved.py::t": 9.0, "fresh.py::t": 2.0},
        )
        assert added == 1
        assert rewritten == 1
