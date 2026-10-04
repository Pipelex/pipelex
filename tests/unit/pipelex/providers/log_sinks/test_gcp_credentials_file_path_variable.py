"""The built-in ``gcp`` sink factory resolves a ``${…}`` placeholder in ``credentials_file_path`` through the secrets provider it receives.

The resolved path goes to ``make_gcp_log_sink`` with the placeholder it came from, so the credential errors
can name both. A plain path is handed over as written, an unset one stays unset for Application Default
Credentials, and a variable that does not resolve stops the boot with ``LogSinkVariableError`` naming it.
The settings the factory was handed keep their placeholder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.tools.log.exceptions import LogSinkVariableError
from pipelex.tools.log.log_sink import LogSinkMethod
from tests.helpers.log_sink_variables import DictSecretsProvider, builtin_log_sink_factory, sink_settings_log_config

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

KEY_PATH = "/run/secrets/gcp-logging-key.json"


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
        factory = builtin_log_sink_factory(method=LogSinkMethod.GCP, mocker=mocker)
        log_config = sink_settings_log_config(gcp_credentials_file_path=spelling)

        factory(log_config, secrets_provider=DictSecretsProvider(secrets={"GCP_CREDENTIALS_FILE_PATH": KEY_PATH}))

        (call,) = made_gcp_sinks
        assert call["config"].credentials_file_path == KEY_PATH
        assert call["credentials_file_path_placeholder"] == spelling
        assert log_config.gcp.credentials_file_path == spelling

    def test_a_plain_key_path_is_handed_over_as_written_with_no_placeholder(
        self, mocker: MockerFixture, made_gcp_sinks: list[dict[str, Any]]
    ) -> None:
        factory = builtin_log_sink_factory(method=LogSinkMethod.GCP, mocker=mocker)

        factory(sink_settings_log_config(gcp_credentials_file_path=KEY_PATH), secrets_provider=DictSecretsProvider(secrets={}))

        (call,) = made_gcp_sinks
        assert call["config"].credentials_file_path == KEY_PATH
        assert call["credentials_file_path_placeholder"] is None

    def test_an_unset_key_path_stays_unset_for_application_default_credentials(
        self, mocker: MockerFixture, made_gcp_sinks: list[dict[str, Any]]
    ) -> None:
        factory = builtin_log_sink_factory(method=LogSinkMethod.GCP, mocker=mocker)

        factory(sink_settings_log_config(gcp_credentials_file_path=None), secrets_provider=DictSecretsProvider(secrets={}))

        (call,) = made_gcp_sinks
        assert call["config"].credentials_file_path is None
        assert call["credentials_file_path_placeholder"] is None

    def test_a_key_path_variable_that_does_not_resolve_stops_the_boot_naming_it(
        self, mocker: MockerFixture, made_gcp_sinks: list[dict[str, Any]]
    ) -> None:
        factory = builtin_log_sink_factory(method=LogSinkMethod.GCP, mocker=mocker)

        with pytest.raises(LogSinkVariableError) as exc_info:
            factory(
                sink_settings_log_config(gcp_credentials_file_path="${GCP_CREDENTIALS_FILE_PATH}"), secrets_provider=DictSecretsProvider(secrets={})
            )

        message = str(exc_info.value)
        assert "credentials_file_path" in message
        assert "[runtime.log.gcp]" in message
        assert "GCP_CREDENTIALS_FILE_PATH" in message
        assert made_gcp_sinks == []
