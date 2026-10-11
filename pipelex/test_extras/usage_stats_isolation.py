"""Keep a test session's anonymous usage statistics off, away from the machine's shared state, and away from any host
that is not loopback.

pipelex's own suites and the API server's call these from their root `conftest.py`: no test reports to Pipelex, and no
test touches `~/.mthds/`. A test that exercises the statistics turns them on itself, with a capture server of its own on
loopback.
"""

import atexit
import os
import shutil
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from pipelex.system.usage_stats import usage_stats_client, usage_stats_delivery
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsEnvVar
from pipelex.system.usage_stats.usage_stats_environment import is_loopback_origin
from pipelex.system.usage_stats.usage_stats_state import UsageStatsState
from pipelex.system.usage_stats.usage_stats_transport import PostVerdict

#: A loopback origin nothing listens on: a test that turns statistics on without a capture server of its own posts nowhere.
USAGE_STATS_DEAD_LOOPBACK_ORIGIN = "http://127.0.0.1:9"


def usage_stats_off_environment() -> dict[str, str]:
    """The variables that keep a process's statistics off and its endpoint on loopback, for an environment built from scratch."""
    return {
        UsageStatsEnvVar.TOOL_SWITCH: "0",
        UsageStatsEnvVar.ENDPOINT_OVERRIDE: USAGE_STATS_DEAD_LOOPBACK_ORIGIN,
    }


def turn_usage_stats_off_for_the_session() -> Path:
    """Turn statistics off in this process's environment, which every process it starts inherits, and make a home for its shared state.

    Called when a root `conftest.py` loads, before any test runs and before xdist starts its workers. The home is
    deleted when the process exits.
    """
    os.environ.update(usage_stats_off_environment())
    home = Path(tempfile.mkdtemp(prefix="pipelex-tests-usage-stats-home-"))
    atexit.register(shutil.rmtree, home, ignore_errors=True)
    return home


@contextmanager
def usage_stats_guarded(*, home: Path) -> Generator[None, None, None]:
    """Point the shared state at `home`, and refuse any post, or detached sender, for an origin that is not loopback.

    A refused attempt fails the test that made it, and fails the session when the block ends, since an attempt made on a
    background thread cannot fail a test.
    """
    refused_origins: list[str] = []
    original_post_batch = usage_stats_delivery.post_batch
    original_start_detached_sender = usage_stats_client.start_detached_sender

    def guarded_post_batch(*, origin: str, events: list[dict[str, Any]], timeout_seconds: float) -> PostVerdict:
        if not is_loopback_origin(origin=origin):
            refused_origins.append(origin)
            pytest.fail(f"A test tried to post usage statistics to {origin}, which is not loopback")
        return original_post_batch(origin=origin, events=events, timeout_seconds=timeout_seconds)

    def guarded_start_detached_sender(*, state: UsageStatsState, origin: str) -> bool:
        if not is_loopback_origin(origin=origin):
            refused_origins.append(origin)
            pytest.fail(f"A test tried to start a usage statistics sender for {origin}, which is not loopback")
        return original_start_detached_sender(state=state, origin=origin)

    def make_test_state() -> UsageStatsState:
        return UsageStatsState(home=home)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(UsageStatsState, "make_for_current_home", staticmethod(make_test_state))
        monkeypatch.setattr(usage_stats_delivery, "post_batch", guarded_post_batch)
        monkeypatch.setattr(usage_stats_client, "start_detached_sender", guarded_start_detached_sender)
        yield
    if refused_origins:
        pytest.fail(f"Tests tried to send usage statistics to hosts that are not loopback: {sorted(set(refused_origins))}")
