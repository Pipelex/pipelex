"""A ``package_log_levels`` key is honoured through the stdlib logger hierarchy.

Loggers are named by module, so a package key governs every module under it and a module key,
spelled with dashes in the configuration, is mapped to the dotted logger name.
"""

from __future__ import annotations

import logging
import types
from typing import TYPE_CHECKING

import pytest

from pipelex import log
from pipelex.tools.log.log_levels import LOGGING_LEVEL_VERBOSE, LogLevel

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

SYNTHETIC_PACKAGE = "synthetic_logpkg"
SYNTHETIC_MODULE = f"{SYNTHETIC_PACKAGE}.sub.mod"
SYNTHETIC_SIBLING = f"{SYNTHETIC_PACKAGE}.other"


def _emitter_in_module(*, module_name: str) -> Callable[[str], None]:
    """A function whose globals say it lives in ``module_name``, so a log call from it is attributed there."""

    def emit(message: str) -> None:
        log.info(message)

    return types.FunctionType(emit.__code__, {"__name__": module_name, "log": log}, "emit")


def _own_records(caplog: pytest.LogCaptureFixture, *, name: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == name]


@pytest.fixture
def clean_synthetic_levels() -> Iterator[None]:
    """Whatever level a test sets on the synthetic loggers is undone afterwards."""
    yield
    for logger_name in (SYNTHETIC_PACKAGE, SYNTHETIC_MODULE, SYNTHETIC_SIBLING, __name__):
        logging.getLogger(logger_name).setLevel(logging.NOTSET)


@pytest.mark.usefixtures("clean_synthetic_levels")
class TestPackageLogLevels:
    def test_a_package_level_key_still_governs_its_modules(self, caplog: pytest.LogCaptureFixture) -> None:
        log.set_levels_for_packages({SYNTHETIC_PACKAGE: LogLevel.WARNING})
        emit = _emitter_in_module(module_name=SYNTHETIC_MODULE)

        with caplog.at_level(LOGGING_LEVEL_VERBOSE):
            emit("dropped by the package level")

        assert _own_records(caplog, name=SYNTHETIC_MODULE) == []

    def test_a_module_level_key_is_honoured_through_the_dash_to_dot_mapping(self, caplog: pytest.LogCaptureFixture) -> None:
        log.set_levels_for_packages(
            {
                SYNTHETIC_PACKAGE: LogLevel.WARNING,
                SYNTHETIC_MODULE.replace(".", "-"): LogLevel.DEBUG,
            }
        )
        emit_module = _emitter_in_module(module_name=SYNTHETIC_MODULE)
        emit_sibling = _emitter_in_module(module_name=SYNTHETIC_SIBLING)

        with caplog.at_level(LOGGING_LEVEL_VERBOSE):
            emit_module("kept by the module level")
            emit_sibling("dropped by the package level")

        (kept,) = _own_records(caplog, name=SYNTHETIC_MODULE)
        assert kept.getMessage() == "kept by the module level"
        assert _own_records(caplog, name=SYNTHETIC_SIBLING) == []

    def test_a_module_level_key_on_the_emitting_test_module(self, caplog: pytest.LogCaptureFixture) -> None:
        log.set_levels_for_packages({__name__.replace(".", "-"): LogLevel.WARNING})

        with caplog.at_level(LOGGING_LEVEL_VERBOSE):
            log.info("dropped")
            log.warning("kept")

        messages = [record.getMessage() for record in _own_records(caplog, name=__name__)]
        assert messages == ["kept"]
