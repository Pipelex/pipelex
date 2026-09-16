"""A log call before ``log.configure`` never raises.

A library's log call is never the thing that crashes the process. Before configuration the record
goes to the stdlib's default handling at the stdlib's default level: no handler is installed as a
side effect, nothing is swallowed, and a warning still reaches stderr through ``logging.lastResort``.
"""

from __future__ import annotations

import logging
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from typing import TYPE_CHECKING

from pipelex.tools.log.log import Log
from pipelex.tools.log.log_levels import LOGGING_LEVEL_VERBOSE

if TYPE_CHECKING:
    import pytest


def _own_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == __name__]


class TestLogBeforeConfigure:
    def test_every_level_emits_without_raising_and_installs_no_handler(self, caplog: pytest.LogCaptureFixture) -> None:
        fresh = Log()
        root_handlers_before = list(logging.getLogger().handlers)

        with caplog.at_level(LOGGING_LEVEL_VERBOSE):
            fresh.verbose("verbose")
            fresh.debug("debug")
            fresh.dev("dev")
            fresh.info("info", fields={"files": 1})
            fresh.warning("warning", problem_id="some_problem")
            try:
                msg = "cause"
                raise ValueError(msg)
            except ValueError:
                fresh.error("error", include_exception=True)
            fresh.critical("critical")
            fresh.info({"structured": "content"}, title="Data")

        assert logging.getLogger().handlers == root_handlers_before
        messages = [record.getMessage() for record in _own_records(caplog)]
        assert messages[:5] == ["verbose", "debug", "dev", "info", "warning"]
        assert messages[5].startswith("error\nTraceback")
        assert messages[6] == "critical"
        assert messages[7].startswith("Data:")
        assert all(record.name == __name__ for record in _own_records(caplog))

    def test_a_cold_process_routes_to_the_stdlib_default_handling(self) -> None:
        """Run it for real: a fresh interpreter, no configure, a warning on stderr and an info dropped at the default level."""
        script = "from pipelex import log\nlog.info('an info line')\nlog.warning('a warning line')\nprint('survived')\n"
        completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == "survived"
        assert "a warning line" in completed.stderr
        assert "an info line" not in completed.stderr
