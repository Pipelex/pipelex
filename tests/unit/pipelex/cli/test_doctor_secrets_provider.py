"""The doctor builds the configured secrets provider before the log sink, as boot does, or says in a row what stopped it.

The provider is handed to the sink, and it is built even when logging was configured before the doctor
ran, since the models row resolves the backends' credentials through it. A factory that fails is quoted
redacted, with the shipped patterns and the configured ones, since a row reaches the console and the
agent's JSON without passing through any sink.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.cli.commands import doctor_cmd
from pipelex.cli.commands.doctor_cmd import discover_doctor_runtime
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar
from pipelex.tools.log.log import log
from pipelex.tools.log.log_sink import LogSink, LogSinkMethod
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.secrets_config import SecretsProviderConfig
from tests.helpers.doctor_log_sink import NullLogSink, assert_the_fallback_console_sink_is_installed_on_stderr, doctor_log_config

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture

    from pipelex.plugins.log_sink_registry import LogSinkFactoryFn
    from pipelex.plugins.secrets_provider_registry import SecretsProviderFactoryFn
    from pipelex.system.configuration.configs import PipelexConfig
    from pipelex.tools.log.log_config import LogConfig
    from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

EXTERNAL_SECRETS_METHOD = "vault"
VAULT_TOKEN = "hvs-0123456789abcdef0123"
VAULT_SESSION = "vault-session-0123456789ab"
VAULT_SESSION_PATTERN = r"vault-session-[0-9a-f]{12}"


class _VaultSecretsProvider(EnvSecretsProvider):
    """The provider an external ``vault`` method builds; only its identity matters here."""


class _SinkFactoryRecorder:
    """A ``json`` sink factory that records the provider it was handed."""

    def __init__(self) -> None:
        self.handed: list[SecretsProviderAbstract] = []

    def __call__(self, _config: LogConfig, /, *, secrets_provider: SecretsProviderAbstract) -> LogSink:
        self.handed.append(secrets_provider)
        return NullLogSink()


def _make_vault_secrets_provider(_config: SecretsProviderConfig) -> SecretsProviderAbstract:
    return _VaultSecretsProvider()


def _make_unreachable_vault_secrets_provider(_config: SecretsProviderConfig) -> SecretsProviderAbstract:
    msg = "the vault at vault.internal:8200 did not answer"
    raise ConnectionError(msg)


def _make_vault_secrets_provider_quoting_its_token(_config: SecretsProviderConfig) -> SecretsProviderAbstract:
    msg = f"the vault refused the request sent with Authorization: Bearer {VAULT_TOKEN}"
    raise ConnectionError(msg)


def _make_vault_secrets_provider_quoting_its_session(_config: SecretsProviderConfig) -> SecretsProviderAbstract:
    msg = f"the vault session {VAULT_SESSION} has expired"
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
        log_config = doctor_log_config(sink=LogSinkMethod.JSON)
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
        log_config = doctor_log_config(sink=LogSinkMethod.JSON)
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
        assert_the_fallback_console_sink_is_installed_on_stderr()

    @pytest.mark.usefixtures("released_log")
    def test_a_secrets_method_nobody_registered_is_a_row_naming_the_registered_ones(self, mocker: MockerFixture) -> None:
        log_config = doctor_log_config(sink=LogSinkMethod.JSON)
        log.configure(log_config=log_config)
        _select_vault_secrets(mocker)
        mocker.patch.object(doctor_cmd, "build_doctor_registrar", return_value=_registrar(secrets_factory=None, sink_factory=_SinkFactoryRecorder()))

        runtime_setup = discover_doctor_runtime(log_config=log_config, installs_log_sink=True)

        assert not runtime_setup.secrets_provider.is_healthy
        assert f"No secrets provider is registered for '{EXTERNAL_SECRETS_METHOD}' in [runtime.secrets]" in runtime_setup.secrets_provider.message
        assert runtime_setup.built_secrets_provider is None

    @pytest.mark.usefixtures("released_log")
    def test_logging_configured_before_the_doctor_keeps_its_sink_and_the_provider_is_still_built(self, mocker: MockerFixture) -> None:
        log_config = doctor_log_config(sink=LogSinkMethod.JSON)
        log.configure(log_config=log_config)
        already_installed = NullLogSink()
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
    def test_a_factory_failure_quoting_a_token_is_redacted_in_the_row(self, mocker: MockerFixture) -> None:
        log_config = doctor_log_config(sink=LogSinkMethod.JSON)
        log.configure(log_config=log_config)
        _select_vault_secrets(mocker)
        registrar = _registrar(secrets_factory=_make_vault_secrets_provider_quoting_its_token, sink_factory=_SinkFactoryRecorder())
        mocker.patch.object(doctor_cmd, "build_doctor_registrar", return_value=registrar)

        runtime_setup = discover_doctor_runtime(log_config=log_config, installs_log_sink=True)

        assert not runtime_setup.secrets_provider.is_healthy
        assert "the vault refused the request sent with Authorization: Bearer [REDACTED]" in runtime_setup.secrets_provider.message
        assert VAULT_TOKEN not in runtime_setup.secrets_provider.message

    @pytest.mark.usefixtures("released_log")
    def test_a_configured_extra_pattern_redacts_the_factory_failure_too(self, mocker: MockerFixture) -> None:
        shipped = doctor_log_config(sink=LogSinkMethod.JSON)
        log_config = shipped.model_copy(update={"redaction": shipped.redaction.model_copy(update={"extra_patterns": [VAULT_SESSION_PATTERN]})})
        log.configure(log_config=log_config)
        _select_vault_secrets(mocker)
        registrar = _registrar(secrets_factory=_make_vault_secrets_provider_quoting_its_session, sink_factory=_SinkFactoryRecorder())
        mocker.patch.object(doctor_cmd, "build_doctor_registrar", return_value=registrar)

        runtime_setup = discover_doctor_runtime(log_config=log_config, installs_log_sink=True)

        assert "the vault session [REDACTED] has expired" in runtime_setup.secrets_provider.message
        assert VAULT_SESSION not in runtime_setup.secrets_provider.message
