"""Unit tests for temporal_connect — API-key resolution, TLS wiring, codec wiring, server selection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.temporal import temporal_connect
from pipelex.temporal.config_temporal import SecretMethod, TemporalServerConfig
from pipelex.temporal.exceptions import TemporalConfigError, TemporalServerError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

TEST_NAMESPACE = "test-ns"
TEST_TARGET_HOST = "temporal.example.com:7233"


def _make_server_config(api_key_method: SecretMethod, api_key_id: str = "") -> TemporalServerConfig:
    return TemporalServerConfig(
        description="Test server",
        target_host=TEST_TARGET_HOST,
        namespace=TEST_NAMESPACE,
        api_key_method=api_key_method,
        api_key_id=api_key_id,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestTemporalConnect:
    @pytest.fixture
    def connect_mocks(self, mocker: MockerFixture) -> dict[str, Any]:
        """Stub the config, the Temporal SDK client, and the secret/env resolvers."""
        config = mocker.MagicMock()
        config.temporal.payload_codec_config.is_enabled = False
        client_cls = mocker.patch.object(temporal_connect, "TemporalClient")
        client_cls.connect = mocker.AsyncMock(return_value=mocker.sentinel.client)
        return {
            "config": config,
            "get_config": mocker.patch.object(temporal_connect, "get_config", return_value=config),
            "connect": client_cls.connect,
            "get_required_env": mocker.patch.object(temporal_connect, "get_required_env", return_value="env-api-key"),
            "get_secret": mocker.patch.object(temporal_connect, "get_secret", return_value="provider-api-key"),
        }

    async def test_no_api_key_connects_without_tls(self, connect_mocks: dict[str, Any]) -> None:
        """api_key_method=none → plain connection: no key, no TLS, no RPC metadata, default converter."""
        server_config = _make_server_config(SecretMethod.NONE)

        client = await temporal_connect.connect_to_temporal_server(server_config=server_config)

        assert client is connect_mocks["connect"].return_value
        connect_kwargs = connect_mocks["connect"].call_args.kwargs
        assert connect_kwargs["target_host"] == TEST_TARGET_HOST
        assert connect_kwargs["namespace"] == TEST_NAMESPACE
        assert connect_kwargs["api_key"] is None
        assert connect_kwargs["tls"] is False
        assert connect_kwargs["rpc_metadata"] == {}
        assert connect_kwargs["data_converter"] is temporal_connect.data_converter
        connect_mocks["get_required_env"].assert_not_called()
        connect_mocks["get_secret"].assert_not_called()

    async def test_env_var_api_key_enables_tls_and_namespace_metadata(self, connect_mocks: dict[str, Any]) -> None:
        """api_key_method=env_var resolves the key from the env and switches on TLS + namespace metadata."""
        server_config = _make_server_config(SecretMethod.ENV_VAR, api_key_id="TEMPORAL_API_KEY")

        await temporal_connect.connect_to_temporal_server(server_config=server_config)

        connect_mocks["get_required_env"].assert_called_once_with("TEMPORAL_API_KEY")
        connect_kwargs = connect_mocks["connect"].call_args.kwargs
        assert connect_kwargs["api_key"] == "env-api-key"
        assert connect_kwargs["tls"] is True
        assert connect_kwargs["rpc_metadata"] == {"temporal-namespace": TEST_NAMESPACE}

    async def test_secret_provider_api_key_resolved_via_get_secret(self, connect_mocks: dict[str, Any]) -> None:
        """api_key_method=secret_provider resolves the key from the secret provider."""
        server_config = _make_server_config(SecretMethod.SECRET_PROVIDER, api_key_id="temporal-key-id")

        await temporal_connect.connect_to_temporal_server(server_config=server_config)

        connect_mocks["get_secret"].assert_called_once_with(secret_id="temporal-key-id")
        connect_kwargs = connect_mocks["connect"].call_args.kwargs
        assert connect_kwargs["api_key"] == "provider-api-key"
        assert connect_kwargs["tls"] is True

    @pytest.mark.parametrize("api_key_method", [SecretMethod.ENV_VAR, SecretMethod.SECRET_PROVIDER])
    async def test_missing_api_key_id_raises_config_error(
        self,
        connect_mocks: dict[str, Any],
        api_key_method: SecretMethod,
    ) -> None:
        """A key-bearing method without an api_key_id is a config error, raised before any connect attempt."""
        server_config = _make_server_config(api_key_method, api_key_id="")

        with pytest.raises(TemporalConfigError, match="api_key_id is required"):
            await temporal_connect.connect_to_temporal_server(server_config=server_config)

        connect_mocks["connect"].assert_not_called()

    async def test_payload_codec_enabled_builds_custom_converter(
        self,
        connect_mocks: dict[str, Any],
        mocker: MockerFixture,
    ) -> None:
        """When the payload codec is enabled, the converter is built from the configured codec."""
        connect_mocks["config"].temporal.payload_codec_config.is_enabled = True
        make_codec = mocker.patch.object(temporal_connect, "make_codec_from_config", return_value=mocker.sentinel.codec)
        make_converter = mocker.patch.object(temporal_connect, "make_data_converter", return_value=mocker.sentinel.converter)

        await temporal_connect.connect_to_temporal_server(server_config=_make_server_config(SecretMethod.NONE))

        make_codec.assert_called_once_with()
        make_converter.assert_called_once_with(payload_codec=mocker.sentinel.codec)
        connect_kwargs = connect_mocks["connect"].call_args.kwargs
        assert connect_kwargs["data_converter"] is mocker.sentinel.converter

    async def test_sdk_runtime_error_wrapped_in_server_error(self, connect_mocks: dict[str, Any]) -> None:
        """A RuntimeError from the SDK connect is wrapped in TemporalServerError with the server description."""
        connect_mocks["connect"].side_effect = RuntimeError("connection refused")
        server_config = _make_server_config(SecretMethod.NONE)

        with pytest.raises(TemporalServerError, match="Failed to connect to Temporal server") as exc_info:
            await temporal_connect.connect_to_temporal_server(server_config=server_config)

        assert server_config.full_description in str(exc_info.value)
        assert "connection refused" in str(exc_info.value)

    async def test_selected_server_connects_with_named_config(self, connect_mocks: dict[str, Any]) -> None:
        """connect_to_temporal_selected_server looks up the named config and connects with it."""
        server_config = _make_server_config(SecretMethod.NONE)
        connect_mocks["config"].temporal.temporal_config.temporal_server_configs = {"local": server_config}

        client = await temporal_connect.connect_to_temporal_selected_server(selected_server_config="local")

        assert client is connect_mocks["connect"].return_value
        connect_kwargs = connect_mocks["connect"].call_args.kwargs
        assert connect_kwargs["target_host"] == TEST_TARGET_HOST

    async def test_selected_server_unknown_name_raises_config_error(self, connect_mocks: dict[str, Any]) -> None:
        """An unknown server-config name is a config error, raised before any connect attempt."""
        connect_mocks["config"].temporal.temporal_config.temporal_server_configs = {"local": _make_server_config(SecretMethod.NONE)}

        with pytest.raises(TemporalConfigError, match="Server config not found for selected server: 'staging'"):
            await temporal_connect.connect_to_temporal_selected_server(selected_server_config="staging")

        connect_mocks["connect"].assert_not_called()

    async def test_connect_to_temporal_uses_configured_selected_server(self, connect_mocks: dict[str, Any]) -> None:
        """connect_to_temporal picks the server named by temporal_config.selected_server."""
        server_config = _make_server_config(SecretMethod.NONE)
        connect_mocks["config"].temporal.temporal_config.selected_server = "chosen"
        connect_mocks["config"].temporal.temporal_config.temporal_server_configs = {"chosen": server_config}

        client = await temporal_connect.connect_to_temporal()

        assert client is connect_mocks["connect"].return_value
        connect_kwargs = connect_mocks["connect"].call_args.kwargs
        assert connect_kwargs["namespace"] == TEST_NAMESPACE
