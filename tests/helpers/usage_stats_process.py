"""Turn this process's usage statistics on for one test, against a home and a loopback origin of the test's own.

Every test session keeps the statistics off (`pipelex.test_extras.usage_stats_isolation`): the environment carries
`PIPELEX_USAGE_STATS=0` and a dead loopback endpoint, and the shared state lives in a temporary home. A test exercising
the statistics takes them back on here, for its own duration: it clears every variable that would say off or mark the
process as in CI or a container, points the shared state at `home`, the endpoint at `origin`, the working directory at
`cwd`, and forgets the process's client before and after, so the process's own boot decided nothing for it.
"""

import os
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest

from pipelex.system.usage_stats import usage_stats_client
from pipelex.system.usage_stats.usage_stats_client import reset_usage_stats_for_tests
from pipelex.system.usage_stats.usage_stats_contract import CI_VARIABLES, CONTAINER_MARKER_VARIABLES, UsageStatsEnvVar
from pipelex.system.usage_stats.usage_stats_state import UsageStatsState
from pipelex.test_extras.usage_stats_isolation import USAGE_STATS_DEAD_LOOPBACK_ORIGIN

#: The variables that decide a process's statistics, cleared before a test sets the ones it needs.
DECIDING_VARIABLES: tuple[str, ...] = (
    UsageStatsEnvVar.DO_NOT_TRACK,
    UsageStatsEnvVar.TOOL_SWITCH,
    UsageStatsEnvVar.DEBUG,
    UsageStatsEnvVar.ENDPOINT_OVERRIDE,
    UsageStatsEnvVar.HOST,
    *CI_VARIABLES,
    *CONTAINER_MARKER_VARIABLES,
)


def make_project_dir(*, parent: Path) -> Path:
    """A project root of the test's own, marked by `.git`, so no project around the test's checkout is read."""
    project_dir = parent / "project"
    (project_dir / ".git").mkdir(parents=True, exist_ok=True)
    return project_dir


def stats_on_environment(*, origin: str = USAGE_STATS_DEAD_LOOPBACK_ORIGIN) -> dict[str, str]:
    """An environment for a child process with statistics on, posting to `origin`, and nothing else deciding them."""
    environment = {name: value for name, value in os.environ.items() if name not in DECIDING_VARIABLES}
    environment[UsageStatsEnvVar.ENDPOINT_OVERRIDE] = origin
    return environment


def _never_a_container(*, env: Mapping[str, str]) -> bool:
    del env
    return False


@contextmanager
def usage_stats_switched_on(
    *,
    monkeypatch: pytest.MonkeyPatch,
    home: Path,
    cwd: Path,
    origin: str = USAGE_STATS_DEAD_LOOPBACK_ORIGIN,
    is_debug: bool = False,
) -> Generator[UsageStatsState, None, None]:
    """Statistics on for the block, with their shared state under `home`; yields that state."""
    for name in DECIDING_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(UsageStatsEnvVar.ENDPOINT_OVERRIDE, origin)
    if is_debug:
        monkeypatch.setenv(UsageStatsEnvVar.DEBUG, "1")
    state = UsageStatsState(home=home)

    def make_state() -> UsageStatsState:
        return state

    monkeypatch.setattr(UsageStatsState, "make_for_current_home", staticmethod(make_state))
    # A machine that is a container would deliver in-process: the tests decide where they deliver, not the machine.
    monkeypatch.setattr(usage_stats_client, "is_container", _never_a_container)
    monkeypatch.chdir(cwd)
    reset_usage_stats_for_tests()
    try:
        yield state
    finally:
        reset_usage_stats_for_tests()
