import json
from pathlib import Path

import pytest
from pytest_mock import MockerFixture, MockType

from tests.helpers.slow_tests import DURATIONS_FILE_NAME, SLOW_MARKER_NAME, SLOW_TEST_SECONDS_OPTION, apply_slow_marker, mark_slow_tests
from tests.unit.repo.cases import SlowTestMarkerTestData


def _make_item(*, mocker: MockerFixture, node_id: str) -> MockType:
    item: MockType = mocker.MagicMock(spec=pytest.Item)
    item.nodeid = node_id
    return item


def _added_marker_names(item: MockType) -> list[str]:
    return [call.args[0].name for call in item.add_marker.call_args_list]


def _make_config(*, mocker: MockerFixture, threshold_seconds: float | None, root: Path) -> MockType:
    config: MockType = mocker.MagicMock(spec=pytest.Config)
    config.rootpath = root
    config.getoption.return_value = threshold_seconds
    return config


class TestSlowTestMarker:
    @pytest.mark.parametrize(
        ("node_id", "expected_markers"),
        [
            (SlowTestMarkerTestData.ABOVE_NODE_ID, [SLOW_MARKER_NAME]),
            (SlowTestMarkerTestData.AT_NODE_ID, [SLOW_MARKER_NAME]),
            (SlowTestMarkerTestData.BELOW_NODE_ID, []),
            (SlowTestMarkerTestData.MISSING_NODE_ID, []),
        ],
    )
    def test_marks_only_tests_recorded_at_or_above_the_threshold(self, mocker: MockerFixture, node_id: str, expected_markers: list[str]) -> None:
        """Above or at the threshold is slow; below it, or absent from the map, is not."""
        item = _make_item(mocker=mocker, node_id=node_id)
        marked_count = mark_slow_tests(
            items=[item],
            durations=SlowTestMarkerTestData.DURATIONS,
            threshold_seconds=SlowTestMarkerTestData.THRESHOLD_SECONDS,
        )
        assert _added_marker_names(item) == expected_markers
        assert marked_count == len(expected_markers)

    def test_reads_the_committed_map_at_the_root_and_marks_through_the_option(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """The hook body reads `.test_durations` under the root directory and marks every slow item in one pass."""
        (tmp_path / DURATIONS_FILE_NAME).write_text(json.dumps(SlowTestMarkerTestData.DURATIONS), encoding="utf-8")
        config = _make_config(mocker=mocker, threshold_seconds=SlowTestMarkerTestData.THRESHOLD_SECONDS, root=tmp_path)
        items = {
            node_id: _make_item(mocker=mocker, node_id=node_id)
            for node_id in (
                SlowTestMarkerTestData.ABOVE_NODE_ID,
                SlowTestMarkerTestData.AT_NODE_ID,
                SlowTestMarkerTestData.BELOW_NODE_ID,
                SlowTestMarkerTestData.MISSING_NODE_ID,
            )
        }
        marked_count = apply_slow_marker(config=config, items=list(items.values()))
        config.getoption.assert_called_once_with(SLOW_TEST_SECONDS_OPTION)
        assert marked_count == 2
        assert _added_marker_names(items[SlowTestMarkerTestData.ABOVE_NODE_ID]) == [SLOW_MARKER_NAME]
        assert _added_marker_names(items[SlowTestMarkerTestData.AT_NODE_ID]) == [SLOW_MARKER_NAME]
        assert _added_marker_names(items[SlowTestMarkerTestData.BELOW_NODE_ID]) == []
        assert _added_marker_names(items[SlowTestMarkerTestData.MISSING_NODE_ID]) == []

    def test_no_threshold_marks_nothing(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Without `--slow-test-seconds` nothing is marked, and the map is not even read."""
        load_spy = mocker.patch("tests.helpers.slow_tests.load_duration_map")
        config = _make_config(mocker=mocker, threshold_seconds=None, root=tmp_path)
        item = _make_item(mocker=mocker, node_id=SlowTestMarkerTestData.ABOVE_NODE_ID)
        assert apply_slow_marker(config=config, items=[item]) == 0
        assert _added_marker_names(item) == []
        load_spy.assert_not_called()

    @pytest.mark.parametrize("threshold_seconds", [0.0, -1.0])
    def test_refuses_a_threshold_that_is_not_positive(self, mocker: MockerFixture, tmp_path: Path, threshold_seconds: float) -> None:
        """A zero or negative threshold would mark every recorded test, so it is a usage error."""
        config = _make_config(mocker=mocker, threshold_seconds=threshold_seconds, root=tmp_path)
        with pytest.raises(pytest.UsageError, match=SLOW_TEST_SECONDS_OPTION):
            apply_slow_marker(config=config, items=[])
