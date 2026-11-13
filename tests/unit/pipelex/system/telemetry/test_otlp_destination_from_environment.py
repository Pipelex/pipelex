from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.system.telemetry.telemetry_config import TelemetryRedactionConfig
from pipelex.system.telemetry.telemetry_identity import RunIdentityPolicy
from pipelex.system.telemetry.telemetry_loader import load_telemetry_config
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

pytestmark = pytest.mark.usefixtures("no_pipelex_home")

# A Sentry-shaped destination, written as an operator writes it: nothing about it is Sentry-specific to Pipelex.
_TELEMETRY_TOML = """
join_host_trace = true

[custom_posthog]
mode = "anonymous"
api_key = "phc_test"

[custom_posthog.tracing]
enabled = true

[[otlp]]
name = "errors"
endpoint = "${env:TEST_OTLP_TRACES_ENDPOINT}"
headers = { "x-sentry-auth" = "${env:TEST_OTLP_AUTH_HEADER}" }
"""

_ENDPOINT = "https://o0.ingest.example.test/api/1/integration/otlp/v1/traces"
_AUTH_HEADER = "sentry sentry_key=public-key-for-tests"


class TestOtlpDestinationFromEnvironment:
    def test_an_otlp_endpoint_and_auth_header_from_the_environment_reach_the_exporter(
        self, tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An arbitrary endpoint and arbitrary headers, resolved from the environment, are what the OTLP span exporter is built with."""
        fake_home = tmp_path / "home"
        global_dir = fake_home / ".pipelex"
        global_dir.mkdir(parents=True)
        (global_dir / "telemetry.toml").write_text(_TELEMETRY_TOML)
        project_root = tmp_path / "project"
        (project_root / ".git").mkdir(parents=True)
        mocker.patch.object(Path, "home", return_value=fake_home)
        mocker.patch.object(Path, "cwd", return_value=project_root)
        monkeypatch.setenv("TEST_OTLP_TRACES_ENDPOINT", _ENDPOINT)
        monkeypatch.setenv("TEST_OTLP_AUTH_HEADER", _AUTH_HEADER)

        telemetry_config = load_telemetry_config(secrets_provider=EnvSecretsProvider())

        assert telemetry_config.join_host_trace is True
        assert telemetry_config.operator_span_destinations() == ["custom_posthog", "otlp:errors"]
        (otlp_config,) = telemetry_config.otlp
        assert otlp_config.endpoint == _ENDPOINT
        assert otlp_config.headers == {"x-sentry-auth": _AUTH_HEADER}

        otlp_exporter_class = mocker.patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter")
        _, provider = OtelFactory.make_ai_tracer(
            custom_fallback_distinct_id=None,
            custom_run_identity_policy=RunIdentityPolicy.NONE,
            custom_posthog_client=None,
            custom_redaction_config=TelemetryRedactionConfig.make_from_posthog_config(posthog_config=None),
            otlp_exporters=telemetry_config.otlp,
            langfuse_config=None,
        )
        try:
            otlp_exporter_class.assert_called_once_with(endpoint=_ENDPOINT, headers={"x-sentry-auth": _AUTH_HEADER})
        finally:
            provider.shutdown()
