import os
from collections.abc import Generator

import pytest
from pipelex.test_extras.usage_stats_isolation import turn_usage_stats_off_for_the_session, usage_stats_guarded

# Set a placeholder for COMPLETION_CALLBACK_SECRET so tests that give /start a completion
# target never depend on the developer's shell env. CAVEAT: `make` test targets export
# every `.env` key NAME into the child env (including commented-out ones) as
# EMPTY strings, and `setdefault` cannot replace an existing empty value — so
# tests that verify the callback signature must pin the secret themselves via
# `mocker.patch.dict(os.environ, ...)` (see tests/unit/test_protocol_conformance.py).
os.environ.setdefault("COMPLETION_CALLBACK_SECRET", "test-placeholder-completion-callback-secret")

pytest_plugins = [
    "pipelex.test_extras.shared_pytest_plugins",
]

# Anonymous usage statistics: no test reports to Pipelex, and none touches this machine's shared state in `~/.mthds/`.
# The server boots in the `fastapi` integration mode, which reports, so its tests turn statistics off in the environment
# when this conftest loads, and `isolate_usage_stats` guards the process.
USAGE_STATS_TEST_HOME = turn_usage_stats_off_for_the_session()


@pytest.fixture(scope="session", autouse=True)
def isolate_usage_stats() -> Generator[None, None, None]:
    """Keep the shared statistics state in a temporary home, and fail any attempt to send to a host that is not loopback."""
    with usage_stats_guarded(home=USAGE_STATS_TEST_HOME):
        yield
