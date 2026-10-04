"""A boot on the ``otlp`` sink resolves a header naming a secret for the exporter, and nowhere else.

The configuration keeps the placeholder, so the resolved token reaches the exporter it authenticates and
no record, no line on stdout or stderr and no reading of the configuration carries it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter

from pipelex import log
from pipelex.config import get_config
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.log.log_sink import LogSinkMethod
from tests.helpers.log_sink_variables import DictSecretsProvider

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture

COLLECTOR_TOKEN = "collector-token-0123456789abcdef"
OTLP_EXPORTER_PATH = "opentelemetry.exporter.otlp.proto.http._log_exporter.OTLPLogExporter"


class _RecordingOtlpExporter(InMemoryLogRecordExporter):
    """Stands in for the OTLP HTTP exporter: keeps what it was built with and what it was asked to export."""

    built: ClassVar[list[_RecordingOtlpExporter]] = []

    def __init__(self, *, endpoint: str | None = None, headers: dict[str, str] | None = None, **_kwargs: Any) -> None:
        super().__init__()
        self.endpoint = endpoint
        self.headers = headers
        _RecordingOtlpExporter.built.append(self)


@pytest.fixture(autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: this module boots per test and tears down."""
    Pipelex.teardown_if_needed()
    yield
    Pipelex.teardown_if_needed()


def _test_integration_mode() -> IntegrationMode:
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestOtlpSinkHeaderSecretAtBoot:
    def test_the_header_is_resolved_for_the_exporter_while_the_config_and_every_record_keep_the_token_out(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _RecordingOtlpExporter.built.clear()
        mocker.patch(OTLP_EXPORTER_PATH, _RecordingOtlpExporter)

        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            secrets_provider=DictSecretsProvider(secrets={"OTLP_COLLECTOR_TOKEN": COLLECTOR_TOKEN}),
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
