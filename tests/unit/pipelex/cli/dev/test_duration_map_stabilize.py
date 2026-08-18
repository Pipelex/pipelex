"""Unit tests for the stabilisation policy: keep a recorded value that has not meaningfully moved.

This is what keeps the committed `.test_durations` diff small. Timings never repeat exactly, so a
re-measurement rewrites essentially every line unless values within tolerance are held steady — and
that diff once grew large enough that automated PR reviewers declined to read the branch.
"""

from __future__ import annotations

from pipelex.cli.dev_cli.commands.duration_map import ABSOLUTE_TOLERANCE, RELATIVE_TOLERANCE, ROUNDING_DECIMALS, stabilize


class TestDurationMapStabilize:
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

    def test_an_unrounded_recorded_value_is_rewritten_onto_the_rounded_grid(self) -> None:
        """Otherwise an in-tolerance entry keeps its long float forever and the file never converges."""
        stabilized = stabilize(previous={"a.py::t": 0.0726180839992594}, current={"a.py::t": 0.0726180839992594})
        assert stabilized == {"a.py::t": 0.0726}

    def test_normalisation_settles_after_one_pass(self) -> None:
        """The wholesale rewrite is a one-time cost, not something every refresh pays."""
        once = stabilize(previous={"a.py::t": 0.0726180839992594}, current={"a.py::t": 0.0726180839992594})
        assert stabilize(previous=once, current={"a.py::t": 0.0726180839992594}) == once
