"""The emitting module is derived from one frame lookup, and loggers are named by module.

The old dispatch walked ``inspect.stack()`` and called ``inspect.getmodule`` on every frame for every
line, which on a slow container filesystem cost more than a second per line. The module now comes
from a frame at a fixed depth and the logger is named after it.
"""

from __future__ import annotations

import inspect
import logging
import types
from pathlib import Path
from typing import TYPE_CHECKING

from pipelex import log
from pipelex.tools.log.log_levels import LOGGING_LEVEL_VERBOSE

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest
    from pytest_mock import MockerFixture

SYNTHETIC_MODULE = "synthetic_logpkg.sub.mod"


def _emitter_in_module(*, module_name: str) -> Callable[[str], None]:
    """A function whose globals say it lives in ``module_name``, so a log call from it is attributed there."""

    def emit(message: str) -> None:
        log.info(message)

    return types.FunctionType(emit.__code__, {"__name__": module_name, "log": log}, "emit")


def _own_records(caplog: pytest.LogCaptureFixture, *, name: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == name]


class TestLoggerNames:
    def test_the_logger_is_named_after_the_emitting_module(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log.info("from the test module")

        (record,) = _own_records(caplog, name=__name__)
        assert record.name == __name__
        assert Path(record.pathname).resolve() == Path(__file__).resolve()
        assert record.funcName == "test_the_logger_is_named_after_the_emitting_module"
        assert record.lineno > 0

    def test_a_nested_module_gets_its_qualified_name(self, caplog: pytest.LogCaptureFixture) -> None:
        emit = _emitter_in_module(module_name=SYNTHETIC_MODULE)
        with caplog.at_level(logging.INFO):
            emit("from a synthetic module")

        (record,) = _own_records(caplog, name=SYNTHETIC_MODULE)
        assert record.getMessage() == "from a synthetic module"

    def test_no_stack_walk_happens_on_emission(self, caplog: pytest.LogCaptureFixture, mocker: MockerFixture) -> None:
        """Every level emits with ``inspect.stack`` and ``inspect.getmodule`` patched to raise."""

        def refuse(*_args: object, **_kwargs: object) -> object:
            msg = "the log dispatch must not walk the stack"
            raise AssertionError(msg)

        mocker.patch.object(inspect, "stack", refuse)
        mocker.patch.object(inspect, "getmodule", refuse)

        with caplog.at_level(LOGGING_LEVEL_VERBOSE):
            log.verbose("verbose")
            log.debug("debug")
            log.dev("dev")
            log.info("info")
            log.warning("warning")
            log.error("error")
            log.critical("critical")
            log.info({"structured": True})

        messages = [record.getMessage() for record in _own_records(caplog, name=__name__)]
        assert messages[:7] == ["verbose", "debug", "dev", "info", "warning", "error", "critical"]
        assert len(messages) == 8
