"""A boot with ``sink = "json"`` carries no Rich handler on the root logger, and each line it writes is one JSON object.

The hosted plane's runner and worker select this sink; this is the shape a log agent ingests.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest
from rich.logging import RichHandler

from pipelex import log
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.log.json_log_sink import LOGGER_KEY, MESSAGE_KEY, SEVERITY_KEY, JsonLogSink
from pipelex.tools.log.log_sink import LogSinkMethod

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: this module boots per test and tears down."""
    Pipelex.teardown_if_needed()
    yield
    Pipelex.teardown_if_needed()


def _test_integration_mode() -> IntegrationMode:
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestLogSinkJsonBoot:
    def test_json_boot_has_no_rich_handler_and_writes_one_json_object_per_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            config_overrides={"runtime": {"log": {"sink": LogSinkMethod.JSON.value}}},
        )
        with log.context(request_id="req-json"):
            log.info("a line for the agent", fields={"files": 3})

        assert isinstance(log.sink, JsonLogSink)
        root_handlers = logging.getLogger().handlers
        assert log.sink.handler in root_handlers
        assert not any(isinstance(handler, RichHandler) for handler in root_handlers)

        captured = capsys.readouterr()
        assert captured.out == ""
        lines = [line for line in captured.err.splitlines() if line]
        parsed = [json.loads(line) for line in lines]
        assert all(isinstance(line, dict) for line in parsed)
        (own,) = [line for line in parsed if line[LOGGER_KEY] == __name__]
        assert own[MESSAGE_KEY] == "a line for the agent"
        assert own[SEVERITY_KEY] == "INFO"
        assert own["files"] == 3
        assert own["request_id"] == "req-json"
        assert "\x1b" not in captured.err
