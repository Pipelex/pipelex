"""Construction tests for the GatewayCompletionsFactory OpenAI client and extras delegation.

These patch the GatewayFactory accessors and the SDK client constructor — they never touch
the network. Transport retry wiring (``max_retries``) is pinned separately in
``tests/unit/pipelex/plugins/test_transport_retry_wiring.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.plugins.gateway.gateway_completions_factory import GatewayCompletionsFactory
from pipelex.plugins.gateway.gateway_exceptions import GatewayFactoryError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_FACTORY_NAMESPACE = "pipelex.plugins.gateway.gateway_completions_factory"


def _patch_gateway_accessors(
    mocker: MockerFixture,
    is_debug_enabled: bool,
    endpoint: str,
    api_key: str,
) -> None:
    mocker.patch(f"{_FACTORY_NAMESPACE}.GatewayFactory.is_debug_enabled", return_value=is_debug_enabled)
    mocker.patch(f"{_FACTORY_NAMESPACE}.GatewayFactory.get_endpoint", return_value=endpoint)
    mocker.patch(f"{_FACTORY_NAMESPACE}.GatewayFactory.get_api_key", return_value=api_key)
    config = mocker.MagicMock()
    config.cogt.transport_max_retries = 2
    mocker.patch(f"{_FACTORY_NAMESPACE}.get_config", return_value=config)


class TestGatewayCompletionsClient:
    """Client construction validates the SDK variant and wires Portkey headers."""

    def test_wrong_sdk_variant_raises_factory_error(self, mocker: MockerFixture) -> None:
        """A plugin whose sdk is not the completions variant is rejected before any client is built."""
        _patch_gateway_accessors(mocker, is_debug_enabled=False, endpoint="https://gateway.test", api_key="gw-test")
        mock_client = mocker.patch("openai.AsyncOpenAI")
        plugin = mocker.MagicMock()
        plugin.sdk = "gateway_responses"

        with pytest.raises(GatewayFactoryError, match="is not supported by 'GatewayCompletionsFactory'"):
            GatewayCompletionsFactory.make_portkey_openai_client_for_completions(plugin=plugin, backend=mocker.MagicMock())

        mock_client.assert_not_called()

    @pytest.mark.parametrize(
        ("is_debug_enabled", "expected_debug_header"),
        [
            (True, "true"),
            (False, "false"),
        ],
    )
    def test_happy_path_wires_endpoint_placeholder_key_and_portkey_headers(
        self,
        mocker: MockerFixture,
        is_debug_enabled: bool,
        expected_debug_header: str,
    ) -> None:
        """The client gets the gateway endpoint as base_url, a non-empty placeholder api_key,
        and default headers built by createHeaders carrying the Portkey api key and debug flag.
        """
        _patch_gateway_accessors(mocker, is_debug_enabled=is_debug_enabled, endpoint="https://gateway.example/v1", api_key="pk-secret")
        mock_client = mocker.patch("openai.AsyncOpenAI")
        plugin = mocker.MagicMock()
        plugin.sdk = "gateway_completions"

        client = GatewayCompletionsFactory.make_portkey_openai_client_for_completions(plugin=plugin, backend=mocker.MagicMock())

        assert client is mock_client.return_value
        mock_client.assert_called_once()
        call_kwargs = mock_client.call_args.kwargs
        assert call_kwargs["base_url"] == "https://gateway.example/v1"
        # Auth goes through Portkey headers; the OpenAI SDK still requires a non-empty api_key.
        assert call_kwargs["api_key"] == "unused-auth-via-portkey-headers"
        default_headers = call_kwargs["default_headers"]
        assert default_headers["x-portkey-api-key"] == "pk-secret"
        assert default_headers["x-portkey-debug"] == expected_debug_header
        assert default_headers["x-portkey-strict-open-ai-compliance"] == "false"

    def test_make_extras_delegates_to_gateway_factory(self, mocker: MockerFixture) -> None:
        """The make_extras override passes all three args through to GatewayFactory.make_extras
        and returns its result unchanged.
        """
        expected_extras: tuple[dict[str, str], dict[str, Any]] = ({"x-portkey-provider": "test-backend"}, {"seed": 42})
        mock_make_extras = mocker.patch(
            f"{_FACTORY_NAMESPACE}.GatewayFactory.make_extras",
            return_value=expected_extras,
        )
        factory = GatewayCompletionsFactory(is_http_url_enabled=True)
        inference_model = mocker.MagicMock()
        inference_job = mocker.MagicMock()

        result = factory.make_extras(inference_model=inference_model, inference_job=inference_job, output_desc="text")

        assert result is expected_extras
        mock_make_extras.assert_called_once_with(inference_model=inference_model, inference_job=inference_job, output_desc="text")
