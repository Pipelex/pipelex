"""The doctor installs the configured log sink, or the console sink with a finding when the token names no registered sink.

Boot stops on an unregistered token. The doctor exists to diagnose exactly that kind of misconfiguration,
so it must not die on where its own lines go: the row says which token was set and which sinks exist.
Once the report is out, the doctor releases the logging it configured, and only that.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pytest
from typing_extensions import override

from pipelex.cli.commands import doctor_cmd
from pipelex.cli.commands.doctor_cmd import install_doctor_log_sink
from pipelex.plugins.log_sink_registry import LogSinkRegistry
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.log import log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_sink import LogSink, LogSinkMethod
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture


def _log_config(*, sink: str) -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate({**config_dict["runtime"]["log"], "sink": sink})


class _NamedSink(LogSink):
    def __init__(self, *, name: str) -> None:
        super().__init__()
        self.name = name

    @override
    def make_handler(self) -> logging.Handler:
        raise NotImplementedError


class _NullSink(LogSink):
    @override
    def make_handler(self) -> logging.Handler:
        return logging.NullHandler()


def _registry() -> LogSinkRegistry:
    return LogSinkRegistry(
        {
            LogSinkMethod.CONSOLE: lambda _config: _NamedSink(name=LogSinkMethod.CONSOLE),
            LogSinkMethod.JSON: lambda _config: _NamedSink(name=LogSinkMethod.JSON),
        }
    )


class TestDoctorLogSink:
    @pytest.fixture
    def released_log(self) -> Iterator[None]:
        """The process-wide facade, released before and after, since the doctor command works on it and not on a fresh instance."""
        log.reset()
        try:
            yield
        finally:
            log.reset()

    @pytest.mark.usefixtures("released_log")
    def test_the_doctor_releases_the_logging_it_configured_once_the_report_is_out(self, mocker: MockerFixture) -> None:
        sink = _NullSink()

        def report_through_a_sink(**_options: Any) -> None:
            log.configure(log_config=_log_config(sink=LogSinkMethod.CONSOLE))
            log.install_sink(sink)
            assert log.sink is sink

        mocker.patch.object(doctor_cmd, "do_doctor_cmd", side_effect=report_through_a_sink)

        doctor_cmd.doctor_cmd(fix=False)

        assert log.sink is None
        assert not log.is_configured
        assert sink.handler not in logging.getLogger().handlers

    @pytest.mark.usefixtures("released_log")
    def test_the_doctor_leaves_logging_an_embedder_configured_before_calling_in(self, mocker: MockerFixture) -> None:
        sink = _NullSink()
        log.configure(log_config=_log_config(sink=LogSinkMethod.CONSOLE))
        log.install_sink(sink)
        mocker.patch.object(doctor_cmd, "do_doctor_cmd")

        doctor_cmd.doctor_cmd(fix=False)

        assert log.sink is sink
        assert log.is_configured

    def test_a_registered_token_installs_that_sink_and_the_row_is_healthy(self, mocker: MockerFixture) -> None:
        install_sink = mocker.patch.object(doctor_cmd.log, "install_sink")

        check = install_doctor_log_sink(registry=_registry(), log_config=_log_config(sink=LogSinkMethod.JSON))

        assert check.is_healthy
        assert LogSinkMethod.JSON in check.message
        (installed,) = install_sink.call_args.args
        assert isinstance(installed, _NamedSink)
        assert installed.name == LogSinkMethod.JSON

    def test_an_unregistered_token_installs_the_console_sink_and_names_the_registered_ones(self, mocker: MockerFixture) -> None:
        install_sink = mocker.patch.object(doctor_cmd.log, "install_sink")

        check = install_doctor_log_sink(registry=_registry(), log_config=_log_config(sink="jsn"))

        assert not check.is_healthy
        assert "'jsn'" in check.message
        assert f"{LogSinkMethod.CONSOLE}, {LogSinkMethod.JSON}" in check.message
        (installed,) = install_sink.call_args.args
        assert isinstance(installed, _NamedSink)
        assert installed.name == LogSinkMethod.CONSOLE
