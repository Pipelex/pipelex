"""The `slow` marker, applied at collection time from the committed `.test_durations` map.

Nobody marks a test `slow` by hand. The root `tests/conftest.py` registers `--slow-test-seconds` and, when it is
given, marks every collected test whose recorded duration is at or above it; the everyday runs (`make agent-test`,
`make agent-test-debug` and the pull-request CI) then deselect them with `-m "... and not slow"`, while the full
runs pass no threshold and keep every test. A test missing from the map is never slow: it has not been measured yet,
and the next `make store-test-durations` gives it a duration. The threshold lives in the Makefile as
`SLOW_TEST_SECONDS`; see `docs/contribute/test-duration-map.md` for the numbers behind it.

The marking runs before pytest's own `-m` deselection and before pytest-split cuts the shards, so a sharded run
balances only the tests it will actually run.
"""

import pytest

from pipelex.cli.dev_cli.commands.duration_map import load_duration_map

SLOW_MARKER_NAME = "slow"
SLOW_TEST_SECONDS_OPTION = "--slow-test-seconds"
DURATIONS_FILE_NAME = ".test_durations"


def add_slow_test_option(*, parser: pytest.Parser) -> None:
    """Register the threshold option. With no value given, nothing is marked."""
    parser.addoption(
        SLOW_TEST_SECONDS_OPTION,
        action="store",
        type=float,
        default=None,
        help=(
            f"Mark `{SLOW_MARKER_NAME}` every test whose duration recorded in {DURATIONS_FILE_NAME} is at or above this many seconds; "
            f"deselect them with `-m 'not {SLOW_MARKER_NAME}'`. Unset (the default), nothing is marked."
        ),
    )


def mark_slow_tests(*, items: list[pytest.Item], durations: dict[str, float], threshold_seconds: float) -> int:
    """Mark `slow` every item whose recorded duration reaches the threshold, and return how many were marked.

    Args:
        items: The collected items, marked in place.
        durations: The node id → seconds map, as committed in `.test_durations`.
        threshold_seconds: The duration at or above which a test is slow.

    Returns:
        The number of items marked.
    """
    slow_marker = pytest.mark.slow
    marked_count = 0
    for item in items:
        recorded_seconds = durations.get(item.nodeid)
        if recorded_seconds is not None and recorded_seconds >= threshold_seconds:
            item.add_marker(slow_marker)
            marked_count += 1
    return marked_count


def apply_slow_marker(*, config: pytest.Config, items: list[pytest.Item]) -> int:
    """Read the threshold and the committed map, then mark the slow items; the body of the conftest hook.

    Args:
        config: The pytest config, holding the threshold option and the root directory the map sits in.
        items: The collected items, marked in place.

    Returns:
        The number of items marked, zero when no threshold was given.

    Raises:
        pytest.UsageError: When the threshold is not a positive number of seconds.
    """
    threshold_seconds: float | None = config.getoption(SLOW_TEST_SECONDS_OPTION)
    if threshold_seconds is None:
        return 0
    if threshold_seconds <= 0:
        msg = f"{SLOW_TEST_SECONDS_OPTION} must be a positive number of seconds, got {threshold_seconds}"
        raise pytest.UsageError(msg)
    durations_path = config.rootpath / DURATIONS_FILE_NAME
    durations = load_duration_map(path=durations_path)
    return mark_slow_tests(items=items, durations=durations, threshold_seconds=threshold_seconds)
