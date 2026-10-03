"""The built-in ``otlp`` and ``gcp`` sink factories resolve ``${…}`` placeholders through the secrets provider they receive.

The values of the ``otlp`` sink's ``headers`` and the ``gcp`` sink's ``credentials_file_path`` are read
through ``substitute_vars``, the syntax the inference backends use: ``${X}`` and ``${secret:X}`` ask the
secrets provider, ``${env:X}`` the environment, ``${env:X|secret:Y}`` one then the other, and a partial
value such as ``"Bearer ${X}"`` keeps its literal part. Header keys are never touched. A variable that does
not resolve stops the boot with ``LogSinkVariableError``, naming the section, the key and the variable and
never a value. The settings the factory was handed keep their placeholders: only the copy handed to the
exporter or the Cloud Logging client holds the resolved value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from typing_extensions import override

from pipelex.plugins.discovery import build_registrar
from pipelex.plugins.log_sink_registry import LogSinkFactoryFn, LogSinkRegistry
from pipelex.providers.builtins import KERNEL_BUILTIN_PLUGINS, KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES, KERNEL_ENTRY_POINT_GROUPS
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.exceptions import LogSinkVariableError
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_sink import LogSinkMethod
from pipelex.tools.log.otlp_log_sink import OtlpLogSink
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.secrets.exceptions import SecretNotFoundError
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture

    from pipelex.system.configuration.configs import PipelexConfig

OTLP_EXPORTER_PATH = "opentelemetry.exporter.otlp.proto.http._log_exporter.OTLPLogExporter"
TOKEN = "a-collector-token-0123456789"
KEY_PATH = "/run/secrets/gcp-logging-key.json"


class _DictSecretsProvider(SecretsProviderAbstract):
    """The secrets a test hands it, and nothing else."""

    def __init__(self, *, secrets: dict[str, str]) -> None:
        self._secrets = secrets

    @override
    def get_required_secret(self, secret_id: str) -> str:
        if secret_id not in self._secrets:
            msg = f"No secret '{secret_id}' in this test provider"
            raise SecretNotFoundError(msg)
        return self._secrets[secret_id]

    @override
    def get_optional_secret(self, secret_id: str) -> str | None:
        return self._secrets.get(secret_id)

    @override
    def get_required_secret_specific_version(self, secret_id: str, *, version_id: str) -> str:
        raise NotImplementedError

    @override
    def get_optional_secret_specific_version(self, secret_id: str, *, version_id: str) -> str | None:
        raise NotImplementedError

    @override
    def set_secret_as_env_var(self, secret_id: str, *, version_id: str = "latest") -> None:
        raise NotImplementedError


class _RecordingOtlpExporter(InMemoryLogRecordExporter):
    """Stands in for the OTLP HTTP exporter: records what it was built with, sends nothing."""

    built: ClassVar[list[_RecordingOtlpExporter]] = []

    def __init__(self, *, endpoint: str | None = None, headers: dict[str, str] | None = None, **_kwargs: Any) -> None:
        super().__init__()
        self.endpoint = endpoint
        self.headers = headers
        _RecordingOtlpExporter.built.append(self)


def _log_config(*, otlp_headers: dict[str, str] | None = None, gcp_credentials_file_path: str | None = None) -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    log_dict = config_dict["runtime"]["log"]
    otlp = {**log_dict["otlp"], "headers": otlp_headers or {}}
    gcp = {**log_dict["gcp"], "credentials_file_path": gcp_credentials_file_path}
    return LogConfig.model_validate({**log_dict, "otlp": otlp, "gcp": gcp})


def _fake_config() -> PipelexConfig:
    from types import SimpleNamespace  # ruff: ignore[import-outside-top-level]
    from typing import cast  # ruff: ignore[import-outside-top-level]

    return cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))


def _builtin_factory(*, method: LogSinkMethod, mocker: MockerFixture) -> LogSinkFactoryFn:
    mocker.patch("pipelex.plugins.discovery._external_entry_points", return_value=[])
    registrar = build_registrar(
        config=_fake_config(),
        boot_orchestrator=None,
        builtin_plugins=KERNEL_BUILTIN_PLUGINS,
        core_unconditional_plugin_names=KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES,
        entry_point_groups=KERNEL_ENTRY_POINT_GROUPS,
    )
    return LogSinkRegistry(registrar.log_sinks).get_required(method=method)


class TestOtlpHeaderVariables:
    @pytest.fixture
    def otlp_factory(self, mocker: MockerFixture) -> Iterator[LogSinkFactoryFn]:
        _RecordingOtlpExporter.built.clear()
        mocker.patch(OTLP_EXPORTER_PATH, _RecordingOtlpExporter)
        built_sinks: list[OtlpLogSink] = []
        factory = _builtin_factory(method=LogSinkMethod.OTLP, mocker=mocker)

        def build(config: LogConfig, /, *, secrets_provider: SecretsProviderAbstract) -> OtlpLogSink:
            sink = factory(config, secrets_provider=secrets_provider)
            assert isinstance(sink, OtlpLogSink)
            built_sinks.append(sink)
            return sink

        yield build
        for sink in built_sinks:
            sink.logger_provider.shutdown()

    def _exported_headers(self) -> dict[str, str] | None:
        (exporter,) = _RecordingOtlpExporter.built
        return exporter.headers

    @pytest.mark.parametrize(
        ("header_value", "expected"),
        [
            ("${OTLP_TOKEN}", TOKEN),
            ("${secret:OTLP_TOKEN}", TOKEN),
            ("Bearer ${OTLP_TOKEN}", f"Bearer {TOKEN}"),
            ("${env:PIPELEX_TEST_UNSET_OTLP_TOKEN|secret:OTLP_TOKEN}", TOKEN),
            ("a plain value", "a plain value"),
        ],
    )
    def test_a_header_value_is_resolved_through_the_secrets_provider(
        self, otlp_factory: LogSinkFactoryFn, monkeypatch: pytest.MonkeyPatch, header_value: str, expected: str
    ) -> None:
        monkeypatch.delenv("PIPELEX_TEST_UNSET_OTLP_TOKEN", raising=False)
        provider = _DictSecretsProvider(secrets={"OTLP_TOKEN": TOKEN})

        otlp_factory(_log_config(otlp_headers={"Authorization": header_value}), secrets_provider=provider)

        assert self._exported_headers() == {"Authorization": expected}

    def test_a_header_value_is_resolved_from_the_environment(self, otlp_factory: LogSinkFactoryFn, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PIPELEX_TEST_OTLP_TOKEN", TOKEN)

        otlp_factory(
            _log_config(otlp_headers={"Authorization": "Bearer ${env:PIPELEX_TEST_OTLP_TOKEN}"}), secrets_provider=_DictSecretsProvider(secrets={})
        )

        assert self._exported_headers() == {"Authorization": f"Bearer {TOKEN}"}

    def test_the_header_keys_are_left_alone(self, otlp_factory: LogSinkFactoryFn) -> None:
        provider = _DictSecretsProvider(secrets={"OTLP_TOKEN": TOKEN, "TENANT": "acme"})

        otlp_factory(_log_config(otlp_headers={"${TENANT}": "${OTLP_TOKEN}"}), secrets_provider=provider)

        assert self._exported_headers() == {"${TENANT}": TOKEN}

    def test_empty_headers_still_reach_the_exporter_as_none(self, otlp_factory: LogSinkFactoryFn) -> None:
        otlp_factory(_log_config(otlp_headers={}), secrets_provider=_DictSecretsProvider(secrets={}))

        assert self._exported_headers() is None

    def test_the_settings_handed_to_the_factory_keep_their_placeholder(self, otlp_factory: LogSinkFactoryFn) -> None:
        log_config = _log_config(otlp_headers={"Authorization": "Bearer ${OTLP_TOKEN}"})

        otlp_factory(log_config, secrets_provider=_DictSecretsProvider(secrets={"OTLP_TOKEN": TOKEN}))

        assert log_config.otlp.headers == {"Authorization": "Bearer ${OTLP_TOKEN}"}

    @pytest.mark.parametrize(
        ("header_value", "variable"),
        [
            ("Bearer ${OTLP_TOKEN}", "OTLP_TOKEN"),
            ("${env:PIPELEX_TEST_UNSET_OTLP_TOKEN}", "PIPELEX_TEST_UNSET_OTLP_TOKEN"),
            ("${env:PIPELEX_TEST_UNSET_OTLP_TOKEN|secret:OTLP_TOKEN}", "env:PIPELEX_TEST_UNSET_OTLP_TOKEN|secret:OTLP_TOKEN"),
            ("${vault:OTLP_TOKEN}", "vault:OTLP_TOKEN"),
        ],
    )
    def test_a_variable_that_does_not_resolve_stops_the_boot_naming_the_section_the_key_and_the_variable(
        self, otlp_factory: LogSinkFactoryFn, monkeypatch: pytest.MonkeyPatch, header_value: str, variable: str
    ) -> None:
        monkeypatch.delenv("PIPELEX_TEST_UNSET_OTLP_TOKEN", raising=False)
        provider = _DictSecretsProvider(secrets={"UNRELATED": TOKEN})

        with pytest.raises(LogSinkVariableError) as exc_info:
            otlp_factory(_log_config(otlp_headers={"Authorization": header_value, "X-Other": "${UNRELATED}"}), secrets_provider=provider)

        message = str(exc_info.value)
        assert "headers.Authorization" in message
        assert "[runtime.log.otlp]" in message
        assert variable in message
        assert "'json' sink" in message
        assert TOKEN not in message
        assert _RecordingOtlpExporter.built == []


class TestGcpCredentialsFilePathVariable:
    @pytest.fixture
    def made_gcp_sinks(self, mocker: MockerFixture) -> list[dict[str, Any]]:
        """What the factory handed ``make_gcp_log_sink``, one entry per call, with no client library involved."""
        calls: list[dict[str, Any]] = []

        def record(**kwargs: Any) -> object:
            calls.append(kwargs)
            return object()

        mocker.patch("pipelex.providers.log_sinks.log_sink_plugin.make_gcp_log_sink", side_effect=record)
        return calls

    @pytest.mark.parametrize("spelling", ["${GCP_CREDENTIALS_FILE_PATH}", "${secret:GCP_CREDENTIALS_FILE_PATH}"])
    def test_the_key_path_is_resolved_through_the_secrets_provider(
        self, mocker: MockerFixture, made_gcp_sinks: list[dict[str, Any]], spelling: str
    ) -> None:
        factory = _builtin_factory(method=LogSinkMethod.GCP, mocker=mocker)
        log_config = _log_config(gcp_credentials_file_path=spelling)

        factory(log_config, secrets_provider=_DictSecretsProvider(secrets={"GCP_CREDENTIALS_FILE_PATH": KEY_PATH}))

        (call,) = made_gcp_sinks
        assert call["config"].credentials_file_path == KEY_PATH
        assert call["credentials_file_path_placeholder"] == spelling
        assert log_config.gcp.credentials_file_path == spelling

    def test_a_plain_key_path_is_handed_over_as_written_with_no_placeholder(
        self, mocker: MockerFixture, made_gcp_sinks: list[dict[str, Any]]
    ) -> None:
        factory = _builtin_factory(method=LogSinkMethod.GCP, mocker=mocker)

        factory(_log_config(gcp_credentials_file_path=KEY_PATH), secrets_provider=_DictSecretsProvider(secrets={}))

        (call,) = made_gcp_sinks
        assert call["config"].credentials_file_path == KEY_PATH
        assert call["credentials_file_path_placeholder"] is None

    def test_an_unset_key_path_stays_unset_for_application_default_credentials(
        self, mocker: MockerFixture, made_gcp_sinks: list[dict[str, Any]]
    ) -> None:
        factory = _builtin_factory(method=LogSinkMethod.GCP, mocker=mocker)

        factory(_log_config(gcp_credentials_file_path=None), secrets_provider=_DictSecretsProvider(secrets={}))

        (call,) = made_gcp_sinks
        assert call["config"].credentials_file_path is None
        assert call["credentials_file_path_placeholder"] is None

    def test_a_key_path_variable_that_does_not_resolve_stops_the_boot_naming_it(
        self, mocker: MockerFixture, made_gcp_sinks: list[dict[str, Any]]
    ) -> None:
        factory = _builtin_factory(method=LogSinkMethod.GCP, mocker=mocker)

        with pytest.raises(LogSinkVariableError) as exc_info:
            factory(_log_config(gcp_credentials_file_path="${GCP_CREDENTIALS_FILE_PATH}"), secrets_provider=_DictSecretsProvider(secrets={}))

        message = str(exc_info.value)
        assert "credentials_file_path" in message
        assert "[runtime.log.gcp]" in message
        assert "GCP_CREDENTIALS_FILE_PATH" in message
        assert made_gcp_sinks == []
