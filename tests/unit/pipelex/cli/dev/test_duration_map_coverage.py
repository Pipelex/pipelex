"""Unit tests for what the refresh decides to measure: which collected tests the map has no entry for.

Coverage is the thing that matters — `pytest-split` imputes an unknown node id at the suite mean, so a
missing entry costs real shard balance while a stale value costs almost none.
"""

from __future__ import annotations

from pipelex.cli.dev_cli.commands.duration_map import file_path_of, missing_node_ids


class TestDurationMapCoverage:
    def test_extracts_the_file_path_from_a_node_id(self) -> None:
        assert file_path_of(node_id="tests/unit/a/test_b.py::TestC::test_d") == "tests/unit/a/test_b.py"

    def test_survives_a_parametrized_id_carrying_colons(self) -> None:
        """Parametrization values routinely embed `::`, so only the FIRST separator may be honoured."""
        assert file_path_of(node_id="tests/unit/test_x.py::test_y[a::b]") == "tests/unit/test_x.py"

    def test_reports_collected_tests_absent_from_the_map(self) -> None:
        missing = missing_node_ids(collected=["a.py::t1", "a.py::t2", "b.py::t3"], durations={"a.py::t1": 1.0})
        assert missing == ["a.py::t2", "b.py::t3"]

    def test_preserves_collection_order(self) -> None:
        """The refresh runs these ids as given, and collection order is what pytest-split assumes."""
        assert missing_node_ids(collected=["z.py::t", "a.py::t"], durations={}) == ["z.py::t", "a.py::t"]

    def test_ignores_recorded_tests_that_were_not_collected(self) -> None:
        """A marker-filtered collection hides much of the suite; those entries are not 'missing'."""
        assert missing_node_ids(collected=["a.py::t1"], durations={"a.py::t1": 1.0, "e2e.py::t9": 2.0}) == []
