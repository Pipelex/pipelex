"""Boot resolves the secrets provider before it installs the log sink, and hands that provider to the sink's factory.

A fake external plugin registers a recording secrets method and a recording sink; the boot selects both.
The secrets factory runs first and the sink factory receives the very provider the hub ends up holding,
or the explicit ``setup(secrets_provider=...)`` one when there is one. The provider is not on the hub
while the sink is built, so the keyword is the only way a sink reaches a secret. A secrets factory that
raises stops the boot before any sink exists, and the lines held until then reach stderr, redacted.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from typing_extensions import override

from pipelex import log
from pipelex.config import get_config
from pipelex.pipelex import Pipelex
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.discovery import GroupedEntryPoint
from pipelex.plugins.plugin_group import PluginGroup
from pipelex.runtime_hub import get_secrets_provider
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.log.log_sink import LogSink, LogSinkMethod
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.secrets.exceptions import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

if TYPE_CHECKING:
    from collections.abc import Generator
    from importlib.metadata import EntryPoint

    from pytest_mock import MockerFixture

    from pipelex.plugins.registrar import PluginRegistrar
    from pipelex.tools.log.log_config import LogConfig
    from pipelex.tools.secrets.secrets_config import SecretsProviderConfig

EXTERNAL_PLUGIN_NAME = "test_secrets_before_sink_ext"
RECORDING_SECRETS_METHOD = "test_recording_secret"
FAILING_SECRETS_METHOD = "test_failing_secret"
RECORDING_SINK_METHOD = "test_recording_sink"
LEAKED_TOKEN = "held-line-token-0123456789abcdef"
COLLECTOR_TOKEN = "collector-token-0123456789abcdef"
OTLP_EXPORTER_PATH = "opentelemetry.exporter.otlp.proto.http._log_exporter.OTLPLogExporter"


class _NoSecretsProvider(SecretsProviderAbstract):
    """A provider holding no secret, whose only use is to be recognised: the tests compare it by identity."""

    @override
    def get_required_secret(self, secret_id: str) -> str:
        msg = f"No secret '{secret_id}' in this test provider"
        raise SecretNotFoundError(msg)

    @override
    def get_optional_secret(self, secret_id: str) -> str | None:
        return None

    @override
    def get_required_secret_specific_version(self, secret_id: str, *, version_id: str) -> str:
        raise NotImplementedError

    @override
    def get_optional_secret_specific_version(self, secret_id: str, *, version_id: str) -> str | None:
        raise NotImplementedError

    @override
    def set_secret_as_env_var(self, secret_id: str, *, version_id: str = "latest") -> None:
        pass


class _TokenSecretsProvider(_NoSecretsProvider):
    """Holds the collector's token and nothing else."""

    @override
    def get_required_secret(self, secret_id: str) -> str:
        if secret_id == "OTLP_COLLECTOR_TOKEN":
            return COLLECTOR_TOKEN
        return super().get_required_secret(secret_id)


class _RecordingOtlpExporter(InMemoryLogRecordExporter):
    """Stands in for the OTLP HTTP exporter: keeps what it was built with and what it was asked to export."""

    built: ClassVar[list[_RecordingOtlpExporter]] = []

    def __init__(self, *, endpoint: str | None = None, headers: dict[str, str] | None = None, **_kwargs: Any) -> None:
        super().__init__()
        self.endpoint = endpoint
        self.headers = headers
        _RecordingOtlpExporter.built.append(self)


class _BootRecorder:
    """What the fake factories saw, in the order they ran, shared across one boot."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.built_provider: SecretsProviderAbstract | None = None
        self.provider_handed_to_sink: SecretsProviderAbstract | None = None
        self.hub_lookup_during_sink_build: Exception | None = None

    def clear(self) -> None:
        self.calls.clear()
        self.built_provider = None
        self.provider_handed_to_sink = None
        self.hub_lookup_during_sink_build = None


_recorder = _BootRecorder()


class _NullLogSink(LogSink):
    @override
    def make_handler(self) -> logging.Handler:
        return logging.NullHandler()


def _make_recording_secrets_provider(_config: SecretsProviderConfig) -> SecretsProviderAbstract:
    _recorder.calls.append("secrets")
    _recorder.built_provider = _NoSecretsProvider()
    return _recorder.built_provider


def _make_failing_secrets_provider(_config: SecretsProviderConfig) -> SecretsProviderAbstract:
    # A line the provider logs before it fails, quoting a credential the way a careless error path would.
    log.warning(f"Could not reach the vault with Authorization: Bearer {LEAKED_TOKEN}")
    msg = "the vault is unreachable"
    raise ConnectionError(msg)


def _make_recording_sink(_config: LogConfig, /, *, secrets_provider: SecretsProviderAbstract) -> LogSink:
    _recorder.calls.append("sink")
    _recorder.provider_handed_to_sink = secrets_provider
    try:
        get_secrets_provider()
    except RuntimeError as exc:
        _recorder.hub_lookup_during_sink_build = exc
    return _NullLogSink()


class _FakeSecretsAndSinkPlugin:
    name = EXTERNAL_PLUGIN_NAME
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_secrets_provider(method=RECORDING_SECRETS_METHOD, factory=_make_recording_secrets_provider)
        registrar.add_secrets_provider(method=FAILING_SECRETS_METHOD, factory=_make_failing_secrets_provider)
        registrar.add_log_sink(method=RECORDING_SINK_METHOD, factory=_make_recording_sink)


@pytest.fixture(autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: this module boots per test and tears down."""
    _recorder.clear()
    Pipelex.teardown_if_needed()
    yield
    Pipelex.teardown_if_needed()


@pytest.fixture(autouse=True)
def external_plugin_fixture(mocker: MockerFixture) -> None:
    fake_entry_point = SimpleNamespace(name=EXTERNAL_PLUGIN_NAME, load=lambda: _FakeSecretsAndSinkPlugin)
    grouped = GroupedEntryPoint(group=PluginGroup.KERNEL, entry_point=cast("EntryPoint", fake_entry_point))
    mocker.patch("pipelex.plugins.discovery._external_entry_points", return_value=[grouped])


def _test_integration_mode() -> IntegrationMode:
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestSecretsBeforeLogSink:
    def test_the_secrets_provider_is_built_before_the_sink_and_handed_to_its_factory(self) -> None:
        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            config_overrides={"runtime": {"secrets": {"method": RECORDING_SECRETS_METHOD}, "log": {"sink": RECORDING_SINK_METHOD}}},
        )

        assert _recorder.calls == ["secrets", "sink"]
        assert _recorder.built_provider is not None
        assert _recorder.provider_handed_to_sink is _recorder.built_provider
        assert get_secrets_provider() is _recorder.built_provider

    def test_the_explicit_secrets_provider_is_the_one_handed_to_the_sink(self) -> None:
        explicit = EnvSecretsProvider()
        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            secrets_provider=explicit,
            config_overrides={"runtime": {"secrets": {"method": RECORDING_SECRETS_METHOD}, "log": {"sink": RECORDING_SINK_METHOD}}},
        )

        assert _recorder.calls == ["sink"]
        assert _recorder.provider_handed_to_sink is explicit
        assert get_secrets_provider() is explicit

    def test_the_provider_is_not_on_the_hub_while_the_sink_is_built(self) -> None:
        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            config_overrides={"runtime": {"secrets": {"method": RECORDING_SECRETS_METHOD}, "log": {"sink": RECORDING_SINK_METHOD}}},
        )

        assert isinstance(_recorder.hub_lookup_during_sink_build, RuntimeError)

    def test_a_secrets_provider_that_fails_stops_the_boot_and_the_held_lines_reach_stderr_redacted(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(ConnectionError, match="the vault is unreachable"):
            Pipelex.make(
                integration_mode=_test_integration_mode(),
                needs_inference=False,
                config_overrides={"runtime": {"secrets": {"method": FAILING_SECRETS_METHOD}, "log": {"sink": RECORDING_SINK_METHOD}}},
            )

        assert "sink" not in _recorder.calls
        assert log.sink is None
        assert Pipelex.get_optional_instance() is None
        stderr = capsys.readouterr().err
        assert "Could not reach the vault with Authorization: Bearer [REDACTED]" in stderr
        assert LEAKED_TOKEN not in stderr


class TestOtlpSinkHeaderSecretAtBoot:
    def test_the_header_is_resolved_for_the_exporter_while_the_config_and_every_record_keep_the_token_out(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _RecordingOtlpExporter.built.clear()
        mocker.patch(OTLP_EXPORTER_PATH, _RecordingOtlpExporter)

        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            secrets_provider=_TokenSecretsProvider(),
            config_overrides={
                "runtime": {
                    "log": {"sink": LogSinkMethod.OTLP.value, "otlp": {"headers": {"Authorization": "Bearer ${OTLP_COLLECTOR_TOKEN}"}}},
                }
            },
        )
        log.info("a line after the boot")
        assert get_config().runtime.log.otlp.headers == {"Authorization": "Bearer ${OTLP_COLLECTOR_TOKEN}"}
        Pipelex.teardown_if_needed()

        (exporter,) = _RecordingOtlpExporter.built
        assert exporter.headers == {"Authorization": f"Bearer {COLLECTOR_TOKEN}"}
        exported = exporter.get_finished_logs()
        assert any(log_data.log_record.body == "a line after the boot" for log_data in exported)
        for log_data in exported:
            assert COLLECTOR_TOKEN not in str(log_data.log_record.body)
            assert COLLECTOR_TOKEN not in str(log_data.log_record.attributes)
        captured = capsys.readouterr()
        assert COLLECTOR_TOKEN not in captured.out
        assert COLLECTOR_TOKEN not in captured.err
