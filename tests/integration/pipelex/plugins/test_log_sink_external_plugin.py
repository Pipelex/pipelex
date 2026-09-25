"""End-to-end: an out-of-tree log sink discovered through a ``pipelex.plugins.kernel`` entry point is
selectable via ``runtime.log.sink`` and installed on the root logger, and a token nobody provides stops
the boot naming the registered ones.

This exercises the whole discovery → selection → install chain the built-in sinks ride, with a fake
external token: a fake entry point loads a plugin registering ``method="test_sink"``, the boot config
selects that token, and the installed sink is the one on the root logger, the boot's own lines replayed
through it.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from typing_extensions import override

from pipelex import log
from pipelex.pipelex import Pipelex
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.discovery import GroupedEntryPoint
from pipelex.plugins.exceptions import UnknownLogSinkError
from pipelex.plugins.plugin_group import PluginGroup
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.log.log_sink import LogSink, LogSinkMethod

if TYPE_CHECKING:
    from collections.abc import Generator
    from importlib.metadata import EntryPoint

    from pytest_mock import MockerFixture

    from pipelex.plugins.registrar import PluginRegistrar
    from pipelex.tools.log.log_config import LogConfig

EXTERNAL_SINK_METHOD = "test_sink"
EXTERNAL_PLUGIN_NAME = "test_log_sink_ext"


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class _RecordingLogSink(LogSink):
    """A minimal out-of-tree sink: its distinct type proves the selection, its records prove the install."""

    def __init__(self) -> None:
        super().__init__()
        self.recording_handler = _RecordingHandler()

    @override
    def make_handler(self) -> logging.Handler:
        return self.recording_handler


def _make_fake_external_sink(_config: LogConfig) -> LogSink:
    return _RecordingLogSink()


class _FakeLogSinkPlugin:
    """An external plugin contributing one log sink under the ``test_sink`` token."""

    name = EXTERNAL_PLUGIN_NAME
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_log_sink(method=EXTERNAL_SINK_METHOD, factory=_make_fake_external_sink)


@pytest.fixture(autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: this module boots per test and tears down."""
    Pipelex.teardown_if_needed()
    yield
    Pipelex.teardown_if_needed()


def _test_integration_mode() -> IntegrationMode:
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestLogSinkExternalPlugin:
    def test_external_sink_is_discovered_selected_and_installed_on_the_root_logger(self, mocker: MockerFixture) -> None:
        """A fake entry point + a config naming its token boots with that external sink's handler on the root logger."""
        fake_entry_point = SimpleNamespace(name=EXTERNAL_PLUGIN_NAME, load=lambda: _FakeLogSinkPlugin)
        # A log sink is a kernel-layer capability, so its dist publishes under the kernel group.
        grouped = GroupedEntryPoint(group=PluginGroup.KERNEL, entry_point=cast("EntryPoint", fake_entry_point))
        mocker.patch("pipelex.plugins.discovery._external_entry_points", return_value=[grouped])

        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            config_overrides={"runtime": {"log": {"sink": EXTERNAL_SINK_METHOD}}},
        )
        log.info("after the boot")

        sink = log.sink
        assert isinstance(sink, _RecordingLogSink)
        assert sink.handler in logging.getLogger().handlers
        messages = [record.getMessage() for record in sink.recording_handler.records]
        assert "after the boot" in messages

        Pipelex.teardown_if_needed()
        assert log.sink is None
        assert sink.handler not in logging.getLogger().handlers

    def test_a_token_nobody_provides_stops_the_boot_naming_the_registered_sinks(self) -> None:
        with pytest.raises(UnknownLogSinkError) as exc_info:
            Pipelex.make(
                integration_mode=_test_integration_mode(),
                needs_inference=False,
                config_overrides={"runtime": {"log": {"sink": "nobody_provides_this"}}},
            )

        assert exc_info.value.method == "nobody_provides_this"
        assert set(exc_info.value.registered_methods) == {method.value for method in LogSinkMethod}
        assert "runtime.log.sink" in str(exc_info.value)
        # The failed boot released the process globals: logging is unconfigured again and no sink is left behind.
        assert log.sink is None
        assert Pipelex.get_optional_instance() is None
