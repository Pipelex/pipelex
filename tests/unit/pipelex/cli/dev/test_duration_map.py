"""Unit tests for the `.test_durations` refresh policies behind `pipelex-dev store-test-durations`."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pipelex.cli.dev_cli.commands.duration_map import (
    ABSOLUTE_TOLERANCE,
    RELATIVE_TOLERANCE,
    ROUNDING_DECIMALS,
    file_path_of,
    load_duration_map,
    missing_node_ids,
    prune_dead_paths,
    stabilize,
    write_duration_map,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestFilePathOf:
    def test_extracts_the_file_path_from_a_node_id(self) -> None:
        assert file_path_of(node_id="tests/unit/a/test_b.py::TestC::test_d") == "tests/unit/a/test_b.py"

    def test_survives_a_parametrized_id_carrying_colons(self) -> None:
        """Parametrization values routinely embed `::`, so only the FIRST separator may be honoured."""
        assert file_path_of(node_id="tests/unit/test_x.py::test_y[a::b]") == "tests/unit/test_x.py"


class TestMissingNodeIds:
    def test_reports_collected_tests_absent_from_the_map(self) -> None:
        missing = missing_node_ids(collected=["a.py::t1", "a.py::t2", "b.py::t3"], durations={"a.py::t1": 1.0})
        assert missing == ["a.py::t2", "b.py::t3"]

    def test_preserves_collection_order(self) -> None:
        """The refresh runs these ids as given, and collection order is what pytest-split assumes."""
        assert missing_node_ids(collected=["z.py::t", "a.py::t"], durations={}) == ["z.py::t", "a.py::t"]

    def test_ignores_recorded_tests_that_were_not_collected(self) -> None:
        """A marker-filtered collection hides much of the suite; those entries are not 'missing'."""
        assert missing_node_ids(collected=["a.py::t1"], durations={"a.py::t1": 1.0, "e2e.py::t9": 2.0}) == []


class TestStabilize:
    def test_keeps_the_recorded_value_when_the_measurement_barely_moved(self) -> None:
        """The whole point: a re-measurement within tolerance must not produce a diff line."""
        stabilized = stabilize(previous={"a.py::t": 1.0}, current={"a.py::t": 1.2})
        assert stabilized == {"a.py::t": 1.0}

    def test_takes_the_new_value_when_the_measurement_moved_beyond_tolerance(self) -> None:
        stabilized = stabilize(previous={"a.py::t": 1.0}, current={"a.py::t": 5.0})
        assert stabilized == {"a.py::t": 5.0}

    def test_absolute_floor_spares_sub_millisecond_jitter(self) -> None:
        """A 20x relative swing on a 0.001s test is noise; without the floor it would rewrite constantly."""
        stabilized = stabilize(previous={"a.py::t": 0.001}, current={"a.py::t": 0.02})
        assert stabilized == {"a.py::t": 0.001}

    def test_relative_term_spares_slow_tests_a_fixed_floor_would_not(self) -> None:
        """On a 10s test a 1s swing is within tolerance, which the absolute floor alone would reject."""
        stabilized = stabilize(previous={"a.py::t": 10.0}, current={"a.py::t": 11.0})
        assert stabilized == {"a.py::t": 10.0}

    def test_new_entries_are_taken_at_their_rounded_measurement(self) -> None:
        stabilized = stabilize(previous={}, current={"a.py::t": 1.23456789})
        assert stabilized == {"a.py::t": round(1.23456789, ROUNDING_DECIMALS)}

    def test_every_stored_value_is_on_the_rounded_grid(self) -> None:
        """The invariant that keeps the file converging to short spellings instead of drifting.

        Covers both branches at once — an entry kept from `previous` and one taken from a fresh
        measurement — because a value written raw on either path reintroduces the churn.
        """
        stabilized = stabilize(
            previous={"kept.py::t": 1.0},
            current={"kept.py::t": 1.000123456, "fresh.py::t": 2.987654321},
        )
        assert stabilized == {node_id: round(value, ROUNDING_DECIMALS) for node_id, value in stabilized.items()}
        assert stabilized["kept.py::t"] == 1.0

    def test_is_idempotent(self) -> None:
        """Re-running the refresh with no new measurement must be a no-op on disk."""
        once = stabilize(previous={}, current={"a.py::t": 1.23456789, "b.py::t": 0.0004471})
        assert stabilize(previous=once, current=once) == once

    def test_drops_entries_absent_from_the_current_map(self) -> None:
        """`current` is the authority on membership; `previous` only supplies stable spellings."""
        assert stabilize(previous={"gone.py::t": 1.0}, current={"a.py::t": 2.0}) == {"a.py::t": 2.0}

    def test_tolerance_is_measured_against_the_recorded_value(self) -> None:
        """Sanity-pins the constants the policy is calibrated on, so a change to them is deliberate."""
        recorded = 1.0
        just_inside = recorded + max(RELATIVE_TOLERANCE * recorded, ABSOLUTE_TOLERANCE) - 0.001
        just_outside = recorded + max(RELATIVE_TOLERANCE * recorded, ABSOLUTE_TOLERANCE) + 0.001
        assert stabilize(previous={"a.py::t": recorded}, current={"a.py::t": just_inside}) == {"a.py::t": recorded}
        assert stabilize(previous={"a.py::t": recorded}, current={"a.py::t": just_outside}) != {"a.py::t": recorded}


class TestPruneDeadPaths:
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


class TestReadWriteRoundTrip:
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


class TestStabilizeNormalisesTheStoredMap:
    def test_an_unrounded_recorded_value_is_rewritten_onto_the_rounded_grid(self) -> None:
        """Otherwise an in-tolerance entry keeps its long float forever and the file never converges."""
        stabilized = stabilize(previous={"a.py::t": 0.0726180839992594}, current={"a.py::t": 0.0726180839992594})
        assert stabilized == {"a.py::t": 0.0726}

    def test_normalisation_settles_after_one_pass(self) -> None:
        """The wholesale rewrite is a one-time cost, not something every refresh pays."""
        once = stabilize(previous={"a.py::t": 0.0726180839992594}, current={"a.py::t": 0.0726180839992594})
        assert stabilize(previous=once, current={"a.py::t": 0.0726180839992594}) == once
