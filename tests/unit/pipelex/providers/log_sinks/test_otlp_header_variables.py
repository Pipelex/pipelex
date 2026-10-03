"""The built-in ``otlp`` sink factory resolves the ``${…}`` placeholders in its header values through the secrets provider it receives.

The values are read through ``substitute_vars``, the syntax the inference backends use: ``${X}`` and
``${secret:X}`` ask the secrets provider, ``${env:X}`` the environment, ``${env:X|secret:Y}`` one then the
other, and a partial value such as ``"Bearer ${X}"`` keeps its literal part. Header keys are never touched. A
variable that does not resolve stops the boot with ``LogSinkVariableError``, naming the section, the key and
the variable and never a value. A resolved value holding a line break, which no HTTP header can carry, stops
the boot with ``LogSinkHeaderValueError``, naming the key and never the value. The settings the factory was
handed keep their placeholders: only the exporter holds the resolved value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter

from pipelex.tools.log.exceptions import LogSinkHeaderValueError, LogSinkVariableError
from pipelex.tools.log.log_sink import LogSinkMethod
from pipelex.tools.log.otlp_log_sink import OtlpLogSink
from tests.helpers.log_sink_variables import DictSecretsProvider, builtin_log_sink_factory, sink_settings_log_config

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture

    from pipelex.plugins.log_sink_registry import LogSinkFactoryFn
    from pipelex.tools.log.log_config import LogConfig
    from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

OTLP_EXPORTER_PATH = "opentelemetry.exporter.otlp.proto.http._log_exporter.OTLPLogExporter"
TOKEN = "a-collector-token-0123456789"


class _RecordingOtlpExporter(InMemoryLogRecordExporter):
    """Stands in for the OTLP HTTP exporter: records what it was built with, sends nothing."""

    built: ClassVar[list[_RecordingOtlpExporter]] = []

    def __init__(self, *, endpoint: str | None = None, headers: dict[str, str] | None = None, **_kwargs: Any) -> None:
        super().__init__()
        self.endpoint = endpoint
        self.headers = headers
        _RecordingOtlpExporter.built.append(self)


class TestOtlpHeaderVariables:
    @pytest.fixture
    def otlp_factory(self, mocker: MockerFixture) -> Iterator[LogSinkFactoryFn]:
        _RecordingOtlpExporter.built.clear()
        mocker.patch(OTLP_EXPORTER_PATH, _RecordingOtlpExporter)
        built_sinks: list[OtlpLogSink] = []
        factory = builtin_log_sink_factory(method=LogSinkMethod.OTLP, mocker=mocker)

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
        provider = DictSecretsProvider(secrets={"OTLP_TOKEN": TOKEN})

        otlp_factory(sink_settings_log_config(otlp_headers={"Authorization": header_value}), secrets_provider=provider)

        assert self._exported_headers() == {"Authorization": expected}

    def test_a_header_value_is_resolved_from_the_environment(self, otlp_factory: LogSinkFactoryFn, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PIPELEX_TEST_OTLP_TOKEN", TOKEN)

        otlp_factory(
            sink_settings_log_config(otlp_headers={"Authorization": "Bearer ${env:PIPELEX_TEST_OTLP_TOKEN}"}),
            secrets_provider=DictSecretsProvider(secrets={}),
        )

        assert self._exported_headers() == {"Authorization": f"Bearer {TOKEN}"}

    def test_the_header_keys_are_left_alone(self, otlp_factory: LogSinkFactoryFn) -> None:
        provider = DictSecretsProvider(secrets={"OTLP_TOKEN": TOKEN, "TENANT": "acme"})

        otlp_factory(sink_settings_log_config(otlp_headers={"${TENANT}": "${OTLP_TOKEN}"}), secrets_provider=provider)

        assert self._exported_headers() == {"${TENANT}": TOKEN}

    def test_empty_headers_still_reach_the_exporter_as_none(self, otlp_factory: LogSinkFactoryFn) -> None:
        otlp_factory(sink_settings_log_config(otlp_headers={}), secrets_provider=DictSecretsProvider(secrets={}))

        assert self._exported_headers() is None

    def test_the_settings_handed_to_the_factory_keep_their_placeholder(self, otlp_factory: LogSinkFactoryFn) -> None:
        log_config = sink_settings_log_config(otlp_headers={"Authorization": "Bearer ${OTLP_TOKEN}"})

        otlp_factory(log_config, secrets_provider=DictSecretsProvider(secrets={"OTLP_TOKEN": TOKEN}))

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
        provider = DictSecretsProvider(secrets={"UNRELATED": TOKEN})

        with pytest.raises(LogSinkVariableError) as exc_info:
            otlp_factory(sink_settings_log_config(otlp_headers={"Authorization": header_value, "X-Other": "${UNRELATED}"}), secrets_provider=provider)

        message = str(exc_info.value)
        assert "headers.Authorization" in message
        assert "[runtime.log.otlp]" in message
        assert variable in message
        assert "'json' sink" in message
        assert TOKEN not in message
        assert _RecordingOtlpExporter.built == []

    @pytest.mark.parametrize("secret", [f"{TOKEN}\n", f"{TOKEN}\r\n", f"{TOKEN}\rX-Injected: 1"])
    def test_a_header_value_resolving_to_a_line_break_stops_the_boot_naming_the_key_alone(self, otlp_factory: LogSinkFactoryFn, secret: str) -> None:
        provider = DictSecretsProvider(secrets={"OTLP_TOKEN": secret})

        with pytest.raises(LogSinkHeaderValueError) as exc_info:
            otlp_factory(sink_settings_log_config(otlp_headers={"Authorization": "Bearer ${OTLP_TOKEN}"}), secrets_provider=provider)

        message = str(exc_info.value)
        assert "headers.Authorization" in message
        assert "[runtime.log.otlp]" in message
        assert "line break" in message
        assert TOKEN not in message
        assert _RecordingOtlpExporter.built == []
