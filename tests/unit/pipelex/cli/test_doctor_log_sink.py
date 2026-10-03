"""The doctor builds the secrets provider, then installs the configured log sink, or the console sink on stderr with a finding when it cannot.

Boot stops on an unregistered token, on a sink that fails to install, on a secrets provider that does not
build and on a plugin registry that does not build. The doctor exists to diagnose exactly that kind of
misconfiguration, so it must not die on where its own lines go: the rows say what was set and what
stopped it. The secrets provider is built first, as at boot, and handed to the sink; it is built even
when logging was configured before the doctor ran, since the models row needs it. Once the report is
out, the doctor releases the logging it configured, and only that.
"""

from __future__ import annotations

import logging
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from rich.logging import RichHandler
from typing_extensions import override

from pipelex.cli.commands import doctor_cmd
from pipelex.cli.commands.doctor_cmd import FALLBACK_LOG_SINK_NOTE, discover_doctor_runtime, install_doctor_log_sink
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.discovery import build_registrar
from pipelex.plugins.exceptions import CoreUnconditionalPluginDisabledError
from pipelex.plugins.log_sink_registry import LogSinkFactoryFn, LogSinkRegistry
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar
from pipelex.providers.builtins import KERNEL_BUILTIN_PLUGINS, KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES, KERNEL_ENTRY_POINT_GROUPS
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.console_log_sink import ConsoleLogSink
from pipelex.tools.log.log import log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_sink import LogSink, LogSinkMethod
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_config import SecretsProviderConfig

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture

    from pipelex.plugins.secrets_provider_registry import SecretsProviderFactoryFn
    from pipelex.system.configuration.configs import PipelexConfig
    from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

EXTERNAL_SECRETS_METHOD = "vault"


def _log_config(*, sink: str, console_log_target: ConsoleTarget = ConsoleTarget.STDERR) -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate({**config_dict["runtime"]["log"], "sink": sink, "console_log_target": console_log_target})


def _assert_the_fallback_console_sink_is_installed_on_stderr() -> None:
    sink = log.sink
    assert isinstance(sink, ConsoleLogSink)
    handler = sink.handler
    assert isinstance(handler, RichHandler)
    assert handler.console.file is sys.stderr


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


def _registry() -> LogSinkRegistry:
    return LogSinkRegistry({LogSinkMethod.CONSOLE: _make_named_console_sink, LogSinkMethod.JSON: _make_named_json_sink})


class _VaultSecretsProvider(EnvSecretsProvider):
    """The provider an external ``vault`` method builds; only its identity matters here."""


class _SinkFactoryRecorder:
    """A ``json`` sink factory that records the provider it was handed."""

    def __init__(self) -> None:
        self.handed: list[SecretsProviderAbstract] = []

    def __call__(self, _config: LogConfig, /, *, secrets_provider: SecretsProviderAbstract) -> LogSink:
        self.handed.append(secrets_provider)
        return _NullSink()


def _make_vault_secrets_provider(_config: SecretsProviderConfig) -> SecretsProviderAbstract:
    return _VaultSecretsProvider()


def _make_unreachable_vault_secrets_provider(_config: SecretsProviderConfig) -> SecretsProviderAbstract:
    msg = "the vault at vault.internal:8200 did not answer"
    raise ConnectionError(msg)


def _registrar(*, secrets_factory: SecretsProviderFactoryFn | None, sink_factory: LogSinkFactoryFn) -> PluginRegistrar:
    """A registrar holding one ``json`` sink and, when given, the external ``vault`` secrets method."""
    registrar = PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[])))))
    registrar.begin_plugin(name="test_vault", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
    if secrets_factory is not None:
        registrar.add_secrets_provider(method=EXTERNAL_SECRETS_METHOD, factory=secrets_factory)
    registrar.add_log_sink(method=LogSinkMethod.JSON, factory=sink_factory)
    return registrar


def _select_vault_secrets(mocker: MockerFixture) -> None:
    secrets_config = SecretsProviderConfig(method=EXTERNAL_SECRETS_METHOD)
    mocker.patch.object(doctor_cmd, "get_config", return_value=SimpleNamespace(runtime=SimpleNamespace(secrets=secrets_config)))


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
        # The handler the install put on the root logger, captured while it is there: the release discards
        # it, and ``sink.handler`` read afterwards builds a new one that could never be on the root.
        installed: list[logging.Handler] = []

        def report_through_a_sink(**_options: Any) -> None:
            log.configure(log_config=_log_config(sink=LogSinkMethod.CONSOLE))
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
        sink = _NullSink()
        log.configure(log_config=_log_config(sink=LogSinkMethod.CONSOLE))
        log.install_sink(sink)
        mocker.patch.object(doctor_cmd, "do_doctor_cmd")

        doctor_cmd.doctor_cmd(fix=False)

        assert log.sink is sink
        assert log.is_configured

    @pytest.mark.usefixtures("released_log")
    def test_a_registered_token_installs_that_sink_and_the_row_is_healthy(self, mocker: MockerFixture) -> None:
        install_sink = mocker.patch.object(doctor_cmd.log, "install_sink")

        check = install_doctor_log_sink(registry=_registry(), log_config=_log_config(sink=LogSinkMethod.JSON), secrets_provider=EnvSecretsProvider())

        assert check.is_healthy
        assert LogSinkMethod.JSON in check.message
        (installed,) = install_sink.call_args.args
        assert isinstance(installed, _NamedSink)
        assert installed.name == LogSinkMethod.JSON

    @pytest.mark.usefixtures("released_log")
    def test_an_unregistered_token_installs_the_console_sink_and_names_the_registered_ones(self, mocker: MockerFixture) -> None:
        install_sink = mocker.patch.object(doctor_cmd.log, "install_sink")

        check = install_doctor_log_sink(registry=_registry(), log_config=_log_config(sink="jsn"), secrets_provider=EnvSecretsProvider())

        assert not check.is_healthy
        assert "'jsn'" in check.message
        assert f"{LogSinkMethod.CONSOLE}, {LogSinkMethod.JSON}" in check.message
        (installed,) = install_sink.call_args.args
        assert isinstance(installed, ConsoleLogSink)

    @pytest.mark.usefixtures("released_log")
    def test_a_sink_that_fails_to_install_on_this_config_is_a_row_and_the_report_goes_on_through_stderr(self) -> None:
        """The shipped default, the console sink, on a console target no sink writes to: the fallback cannot read the same field."""
        log_config = _log_config(sink=LogSinkMethod.CONSOLE, console_log_target=ConsoleTarget.FILE)
        log.configure(log_config=log_config)
        registry = LogSinkRegistry({LogSinkMethod.CONSOLE: _make_console_sink_from_config})

        check = install_doctor_log_sink(registry=registry, log_config=log_config, secrets_provider=EnvSecretsProvider())

        assert not check.is_healthy
        assert "could not be installed" in check.message
        assert "choose stdout or stderr" in check.message
        _assert_the_fallback_console_sink_is_installed_on_stderr()

    @pytest.mark.usefixtures("released_log")
    def test_a_sink_that_failed_after_being_recorded_is_a_row_and_the_installed_sink_is_kept(self) -> None:
        """The failure comes out of the replay, past the point where the sink was recorded, so there is nothing for a fallback to install."""
        log_config = _log_config(sink=LogSinkMethod.JSON)
        log.configure(log_config=log_config)
        log.warning("a record held until the sink arrives")
        registry = LogSinkRegistry({LogSinkMethod.JSON: _make_fails_on_replay_sink})

        check = install_doctor_log_sink(registry=registry, log_config=log_config, secrets_provider=EnvSecretsProvider())

        assert not check.is_healthy
        assert "stderr is closed" in check.message
        assert isinstance(log.sink, _FailsOnReplaySink)

    @pytest.mark.usefixtures("released_log")
    def test_a_plugin_registry_that_does_not_build_is_a_row_and_the_report_goes_on_through_stderr(self, mocker: MockerFixture) -> None:
        log_config = _log_config(sink=LogSinkMethod.JSON)
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
        _assert_the_fallback_console_sink_is_installed_on_stderr()

    @pytest.mark.usefixtures("released_log")
    def test_a_fallback_refused_because_a_sink_is_already_recorded_says_so_and_keeps_that_sink(self) -> None:
        """``install_sink`` records the sink before it replays what the holding handler held, deliberately, so that a replay
        which raises still leaves the sink findable by ``reset``. The fallback therefore cannot assume that a failed
        installation left nothing behind: installing on top would raise in place of the failure it was called to report, and
        a row promising the console fallback would name a sink that never stood in.
        """
        log_config = _log_config(sink=LogSinkMethod.JSON)
        log.configure(log_config=log_config)
        already_recorded = _NullSink()
        log.install_sink(already_recorded)

        check = install_doctor_log_sink(registry=None, log_config=log_config, secrets_provider=EnvSecretsProvider())

        assert not check.is_healthy
        assert "registry did not build" in check.message
        assert "already recorded" in check.message
        assert FALLBACK_LOG_SINK_NOTE not in check.message
        assert log.sink is already_recorded


class TestDoctorSecretsProvider:
    @pytest.fixture
    def released_log(self) -> Iterator[None]:
        log.reset()
        try:
            yield
        finally:
            log.reset()

    @pytest.mark.usefixtures("released_log")
    def test_the_configured_secrets_provider_is_built_first_and_handed_to_the_sink(self, mocker: MockerFixture) -> None:
        log_config = _log_config(sink=LogSinkMethod.JSON)
        log.configure(log_config=log_config)
        _select_vault_secrets(mocker)
        sink_factory = _SinkFactoryRecorder()
        registrar = _registrar(secrets_factory=_make_vault_secrets_provider, sink_factory=sink_factory)
        mocker.patch.object(doctor_cmd, "build_doctor_registrar", return_value=registrar)

        runtime_setup = discover_doctor_runtime(log_config=log_config, installs_log_sink=True)

        assert runtime_setup.secrets_provider.is_healthy
        assert f"'{EXTERNAL_SECRETS_METHOD}'" in runtime_setup.secrets_provider.message
        assert isinstance(runtime_setup.built_secrets_provider, _VaultSecretsProvider)
        assert sink_factory.handed == [runtime_setup.built_secrets_provider]
        assert runtime_setup.log_sink.is_healthy

    @pytest.mark.usefixtures("released_log")
    def test_a_secrets_provider_that_fails_to_build_is_a_row_the_sink_is_not_checked_and_the_report_goes_on_through_stderr(
        self, mocker: MockerFixture
    ) -> None:
        log_config = _log_config(sink=LogSinkMethod.JSON)
        log.configure(log_config=log_config)
        _select_vault_secrets(mocker)
        sink_factory = _SinkFactoryRecorder()
        registrar = _registrar(secrets_factory=_make_unreachable_vault_secrets_provider, sink_factory=sink_factory)
        mocker.patch.object(doctor_cmd, "build_doctor_registrar", return_value=registrar)

        runtime_setup = discover_doctor_runtime(log_config=log_config, installs_log_sink=True)

        assert runtime_setup.plugins.is_healthy
        assert not runtime_setup.secrets_provider.is_healthy
        assert "could not be built" in runtime_setup.secrets_provider.message
        assert "did not answer" in runtime_setup.secrets_provider.message
        assert runtime_setup.built_secrets_provider is None
        assert not runtime_setup.log_sink.is_healthy
        assert "not checked because the secrets provider did not build" in runtime_setup.log_sink.message
        assert sink_factory.handed == []
        _assert_the_fallback_console_sink_is_installed_on_stderr()

    @pytest.mark.usefixtures("released_log")
    def test_a_secrets_method_nobody_registered_is_a_row_naming_the_registered_ones(self, mocker: MockerFixture) -> None:
        log_config = _log_config(sink=LogSinkMethod.JSON)
        log.configure(log_config=log_config)
        _select_vault_secrets(mocker)
        mocker.patch.object(doctor_cmd, "build_doctor_registrar", return_value=_registrar(secrets_factory=None, sink_factory=_SinkFactoryRecorder()))

        runtime_setup = discover_doctor_runtime(log_config=log_config, installs_log_sink=True)

        assert not runtime_setup.secrets_provider.is_healthy
        assert f"No secrets provider is registered for '{EXTERNAL_SECRETS_METHOD}' in [runtime.secrets]" in runtime_setup.secrets_provider.message
        assert runtime_setup.built_secrets_provider is None

    @pytest.mark.usefixtures("released_log")
    def test_logging_configured_before_the_doctor_keeps_its_sink_and_the_provider_is_still_built(self, mocker: MockerFixture) -> None:
        log_config = _log_config(sink=LogSinkMethod.JSON)
        log.configure(log_config=log_config)
        already_installed = _NullSink()
        log.install_sink(already_installed)
        _select_vault_secrets(mocker)
        sink_factory = _SinkFactoryRecorder()
        mocker.patch.object(
            doctor_cmd, "build_doctor_registrar", return_value=_registrar(secrets_factory=_make_vault_secrets_provider, sink_factory=sink_factory)
        )

        runtime_setup = discover_doctor_runtime(log_config=log_config, installs_log_sink=False)

        assert isinstance(runtime_setup.built_secrets_provider, _VaultSecretsProvider)
        assert runtime_setup.secrets_provider.is_healthy
        assert runtime_setup.log_sink.is_healthy
        assert "already configured" in runtime_setup.log_sink.message
        assert sink_factory.handed == []
        assert log.sink is already_installed

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
        log_config = _log_config(sink=LogSinkMethod.OTLP)
        log_config = log_config.model_copy(
            update={"otlp": log_config.otlp.model_copy(update={"headers": {"Authorization": "Bearer ${PIPELEX_TEST_UNSET_COLLECTOR_TOKEN}"}})}
        )
        log.configure(log_config=log_config)

        check = install_doctor_log_sink(registry=LogSinkRegistry(registrar.log_sinks), log_config=log_config, secrets_provider=EnvSecretsProvider())

        assert not check.is_healthy
        assert "`headers.Authorization` under [runtime.log.otlp]" in check.message
        assert "PIPELEX_TEST_UNSET_COLLECTOR_TOKEN" in check.message
        assert FALLBACK_LOG_SINK_NOTE in check.message
        _assert_the_fallback_console_sink_is_installed_on_stderr()
