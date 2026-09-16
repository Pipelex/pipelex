"""The emitting module is derived from one frame lookup, and loggers are named by module.

The old dispatch walked ``inspect.stack()`` and called ``inspect.getmodule`` on every frame for every
line, which on a slow container filesystem cost more than a second per line. The module now comes
from a frame at a fixed depth, the logger is named after it, and a per-module key in
``package_log_levels`` is honoured through the stdlib hierarchy.
"""

from __future__ import annotations

import inspect
import logging
import types
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex import log
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import CallerInfoTemplate, LogConfig
from pipelex.tools.log.log_levels import LOGGING_LEVEL_VERBOSE, LogLevel

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from pytest_mock import MockerFixture

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


class TestCallerInfo:
    @pytest.fixture
    def log_with_caller_info(self) -> Iterator[Log]:
        """A fresh ``Log`` configured with caller info on, torn down so its handler leaves the root logger."""
        from pipelex.system.configuration.config_loader import ConfigLoader  # ruff: ignore[import-outside-top-level]
        from pipelex.tools.misc.toml_utils import load_toml_from_path  # ruff: ignore[import-outside-top-level]

        config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
        log_config = LogConfig.model_validate(config_dict["runtime"]["log"]).model_copy(
            update={"is_caller_info_enabled": True, "caller_info_template": CallerInfoTemplate.FUNC_MODULE_LINE},
        )
        fresh = Log()
        fresh.configure(log_config=log_config)
        try:
            yield fresh
        finally:
            fresh.reset()

    def test_caller_info_names_the_function_module_and_line_without_reading_source(
        self,
        log_with_caller_info: Log,
        caplog: pytest.LogCaptureFixture,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch.object(inspect, "getframeinfo", side_effect=AssertionError("no source lookup"))
        with caplog.at_level(logging.INFO):
            log_with_caller_info.info("located")

        (record,) = _own_records(caplog, name=__name__)
        assert record.funcName == "test_caller_info_names_the_function_module_and_line_without_reading_source"
        assert record.getMessage() == f"{record.funcName} {__name__} {record.lineno}: located"
