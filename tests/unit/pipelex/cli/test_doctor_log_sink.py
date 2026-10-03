"""The doctor installs the configured log sink, or the console sink on stderr with a finding when it cannot.

Boot stops on an unregistered token, on a sink that fails to install, on a sink setting naming a variable
that does not resolve and on a plugin registry that does not build. The doctor exists to diagnose exactly
that kind of misconfiguration, so it must not die on where its own lines go: the row says what was set and
what stopped it, quoting a failure redacted, since a row reaches the reader without passing through any
sink. Once the report is out, the doctor releases the logging it configured, and only that.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from typing_extensions import override

from pipelex.cli.commands import doctor_cmd
from pipelex.cli.commands.doctor_cmd import FALLBACK_LOG_SINK_NOTE, discover_doctor_runtime, install_doctor_log_sink
from pipelex.plugins.discovery import build_registrar
from pipelex.plugins.exceptions import CoreUnconditionalPluginDisabledError
from pipelex.plugins.log_sink_registry import LogSinkRegistry
from pipelex.providers.builtins import KERNEL_BUILTIN_PLUGINS, KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES, KERNEL_ENTRY_POINT_GROUPS
from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.console_log_sink import ConsoleLogSink
from pipelex.tools.log.log import log
from pipelex.tools.log.log_sink import LogSink, LogSinkMethod
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from tests.helpers.doctor_log_sink import NullLogSink, assert_the_fallback_console_sink_is_installed_on_stderr, doctor_log_config

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture

    from pipelex.system.configuration.configs import PipelexConfig
    from pipelex.tools.log.log_config import LogConfig
    from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


COLLECTOR_TOKEN = "collector-token-0123456789abcdef"


class _NamedSink(LogSink):
    def __init__(self, *, name: str) -> None:
        super().__init__()
        self.name = name

    @override
    def make_handler(self) -> logging.Handler:
        raise NotImplementedError


class _UnrecoverableHandler(logging.Handler):
    """Cannot render a record, and cannot say so either: the shape a closed stderr gives a handler at its ``handleError``."""

    @override
    def emit(self, record: logging.LogRecord) -> None:
        msg = "this handler cannot render a record"
        raise RuntimeError(msg)

    @override
    def handleError(self, record: logging.LogRecord) -> None:
        msg = "stderr is closed"
        raise ValueError(msg)


class _FailsOnReplaySink(LogSink):
    """Builds its handler, so the sink is recorded as installed, and then fails on the first record replayed through it."""

    @override
    def make_handler(self) -> logging.Handler:
        return _UnrecoverableHandler()


def _make_named_console_sink(_config: LogConfig, /, *, secrets_provider: SecretsProviderAbstract) -> LogSink:  # ruff: ignore[unused-function-argument] - the LogSinkFactoryFn shape
    return _NamedSink(name=LogSinkMethod.CONSOLE)


def _make_named_json_sink(_config: LogConfig, /, *, secrets_provider: SecretsProviderAbstract) -> LogSink:  # ruff: ignore[unused-function-argument] - the LogSinkFactoryFn shape
    return _NamedSink(name=LogSinkMethod.JSON)


def _make_console_sink_from_config(config: LogConfig, /, *, secrets_provider: SecretsProviderAbstract) -> LogSink:  # ruff: ignore[unused-function-argument] - the LogSinkFactoryFn shape
    return ConsoleLogSink(rich_log_config=config.rich_log, target=config.console_log_target)


def _make_fails_on_replay_sink(_config: LogConfig, /, *, secrets_provider: SecretsProviderAbstract) -> LogSink:  # ruff: ignore[unused-function-argument] - the LogSinkFactoryFn shape
    return _FailsOnReplaySink()


def _make_sink_failing_with_its_token(_config: LogConfig, /, *, secrets_provider: SecretsProviderAbstract) -> LogSink:  # ruff: ignore[unused-function-argument] - the LogSinkFactoryFn shape
    msg = f"the collector refused the exporter built with Authorization: Bearer {COLLECTOR_TOKEN}"
    raise ConnectionError(msg)


def _registry() -> LogSinkRegistry:
    return LogSinkRegistry({LogSinkMethod.CONSOLE: _make_named_console_sink, LogSinkMethod.JSON: _make_named_json_sink})


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
        sink = NullLogSink()
        # The handler the install put on the root logger, captured while it is there: the release discards
        # it, and ``sink.handler`` read afterwards builds a new one that could never be on the root.
        installed: list[logging.Handler] = []

        def report_through_a_sink(**_options: Any) -> None:
            log.configure(log_config=doctor_log_config(sink=LogSinkMethod.CONSOLE))
            log.install_sink(sink)
            assert log.sink is sink
            installed.append(sink.handler)

        mocker.patch.object(doctor_cmd, "do_doctor_cmd", side_effect=report_through_a_sink)

        doctor_cmd.doctor_cmd(fix=False)

        assert log.sink is None
        assert not log.is_configured
        (handler,) = installed
        assert handler not in logging.getLogger().handlers

    @pytest.mark.usefixtures("released_log")
    def test_the_doctor_leaves_logging_an_embedder_configured_before_calling_in(self, mocker: MockerFixture) -> None:
        sink = NullLogSink()
        log.configure(log_config=doctor_log_config(sink=LogSinkMethod.CONSOLE))
        log.install_sink(sink)
        mocker.patch.object(doctor_cmd, "do_doctor_cmd")

        doctor_cmd.doctor_cmd(fix=False)

        assert log.sink is sink
        assert log.is_configured

    @pytest.mark.usefixtures("released_log")
    def test_a_registered_token_installs_that_sink_and_the_row_is_healthy(self, mocker: MockerFixture) -> None:
        install_sink = mocker.patch.object(doctor_cmd.log, "install_sink")

        check = install_doctor_log_sink(
            registry=_registry(), log_config=doctor_log_config(sink=LogSinkMethod.JSON), secrets_provider=EnvSecretsProvider()
        )

        assert check.is_healthy
        assert LogSinkMethod.JSON in check.message
        (installed,) = install_sink.call_args.args
        assert isinstance(installed, _NamedSink)
        assert installed.name == LogSinkMethod.JSON

    @pytest.mark.usefixtures("released_log")
    def test_an_unregistered_token_installs_the_console_sink_and_names_the_registered_ones(self, mocker: MockerFixture) -> None:
        install_sink = mocker.patch.object(doctor_cmd.log, "install_sink")

        check = install_doctor_log_sink(registry=_registry(), log_config=doctor_log_config(sink="jsn"), secrets_provider=EnvSecretsProvider())

        assert not check.is_healthy
        assert "'jsn'" in check.message
        assert f"{LogSinkMethod.CONSOLE}, {LogSinkMethod.JSON}" in check.message
        (installed,) = install_sink.call_args.args
        assert isinstance(installed, ConsoleLogSink)

    @pytest.mark.usefixtures("released_log")
    def test_a_sink_that_fails_to_install_on_this_config_is_a_row_and_the_report_goes_on_through_stderr(self) -> None:
        """The shipped default, the console sink, on a console target no sink writes to: the fallback cannot read the same field."""
        log_config = doctor_log_config(sink=LogSinkMethod.CONSOLE, console_log_target=ConsoleTarget.FILE)
        log.configure(log_config=log_config)
        registry = LogSinkRegistry({LogSinkMethod.CONSOLE: _make_console_sink_from_config})

        check = install_doctor_log_sink(registry=registry, log_config=log_config, secrets_provider=EnvSecretsProvider())

        assert not check.is_healthy
        assert "could not be installed" in check.message
        assert "choose stdout or stderr" in check.message
        assert_the_fallback_console_sink_is_installed_on_stderr()

    @pytest.mark.usefixtures("released_log")
    def test_a_sink_failure_quoting_a_token_is_redacted_in_the_row(self) -> None:
        log_config = doctor_log_config(sink=LogSinkMethod.JSON)
        log.configure(log_config=log_config)
        registry = LogSinkRegistry({LogSinkMethod.JSON: _make_sink_failing_with_its_token})

        check = install_doctor_log_sink(registry=registry, log_config=log_config, secrets_provider=EnvSecretsProvider())

        assert not check.is_healthy
        assert "the collector refused the exporter built with Authorization: Bearer [REDACTED]" in check.message
        assert COLLECTOR_TOKEN not in check.message
        assert_the_fallback_console_sink_is_installed_on_stderr()

    @pytest.mark.usefixtures("released_log")
    def test_a_sink_that_failed_after_being_recorded_is_a_row_and_the_installed_sink_is_kept(self) -> None:
        """The failure comes out of the replay, past the point where the sink was recorded, so there is nothing for a fallback to install."""
        log_config = doctor_log_config(sink=LogSinkMethod.JSON)
        log.configure(log_config=log_config)
        log.warning("a record held until the sink arrives")
        registry = LogSinkRegistry({LogSinkMethod.JSON: _make_fails_on_replay_sink})

        check = install_doctor_log_sink(registry=registry, log_config=log_config, secrets_provider=EnvSecretsProvider())

        assert not check.is_healthy
        assert "stderr is closed" in check.message
        assert isinstance(log.sink, _FailsOnReplaySink)

    @pytest.mark.usefixtures("released_log")
    def test_a_plugin_registry_that_does_not_build_is_a_row_and_the_report_goes_on_through_stderr(self, mocker: MockerFixture) -> None:
        log_config = doctor_log_config(sink=LogSinkMethod.JSON)
        log.configure(log_config=log_config)
        mocker.patch.object(doctor_cmd, "get_config")
        mocker.patch.object(doctor_cmd, "build_registrar", side_effect=CoreUnconditionalPluginDisabledError(plugin_name="storage"))

        runtime_setup = discover_doctor_runtime(log_config=log_config, installs_log_sink=True)

        assert not runtime_setup.plugins.is_healthy
        assert "'storage'" in runtime_setup.plugins.message
        assert not runtime_setup.secrets_provider.is_healthy
        assert "registry did not build" in runtime_setup.secrets_provider.message
        assert runtime_setup.built_secrets_provider is None
        assert not runtime_setup.log_sink.is_healthy
        assert "registry did not build" in runtime_setup.log_sink.message
        assert_the_fallback_console_sink_is_installed_on_stderr()

    @pytest.mark.usefixtures("released_log")
    def test_a_fallback_refused_because_a_sink_is_already_recorded_says_so_and_keeps_that_sink(self) -> None:
        """``install_sink`` records the sink before it replays what the holding handler held, deliberately, so that a replay
        which raises still leaves the sink findable by ``reset``. The fallback therefore cannot assume that a failed
        installation left nothing behind: installing on top would raise in place of the failure it was called to report, and
        a row promising the console fallback would name a sink that never stood in.
        """
        log_config = doctor_log_config(sink=LogSinkMethod.JSON)
        log.configure(log_config=log_config)
        already_recorded = NullLogSink()
        log.install_sink(already_recorded)

        check = install_doctor_log_sink(registry=None, log_config=log_config, secrets_provider=EnvSecretsProvider())

        assert not check.is_healthy
        assert "registry did not build" in check.message
        assert "already recorded" in check.message
        assert FALLBACK_LOG_SINK_NOTE not in check.message
        assert log.sink is already_recorded

    @pytest.mark.usefixtures("released_log")
    def test_a_sink_header_naming_a_variable_that_does_not_resolve_is_a_row_naming_it(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PIPELEX_TEST_UNSET_COLLECTOR_TOKEN", raising=False)
        mocker.patch("pipelex.plugins.discovery._external_entry_points", return_value=[])
        registrar = build_registrar(
            config=cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[])))),
            boot_orchestrator=None,
            builtin_plugins=KERNEL_BUILTIN_PLUGINS,
            core_unconditional_plugin_names=KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES,
            entry_point_groups=KERNEL_ENTRY_POINT_GROUPS,
        )
        log_config = doctor_log_config(sink=LogSinkMethod.OTLP)
        log_config = log_config.model_copy(
            update={"otlp": log_config.otlp.model_copy(update={"headers": {"Authorization": "Bearer ${PIPELEX_TEST_UNSET_COLLECTOR_TOKEN}"}})}
        )
        log.configure(log_config=log_config)

        check = install_doctor_log_sink(registry=LogSinkRegistry(registrar.log_sinks), log_config=log_config, secrets_provider=EnvSecretsProvider())

        assert not check.is_healthy
        assert "`headers.Authorization` under [runtime.log.otlp]" in check.message
        assert "PIPELEX_TEST_UNSET_COLLECTOR_TOKEN" in check.message
        assert FALLBACK_LOG_SINK_NOTE in check.message
        assert_the_fallback_console_sink_is_installed_on_stderr()
