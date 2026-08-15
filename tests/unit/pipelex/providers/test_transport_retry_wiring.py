"""Construction tests for Tier 1 transport-retry wiring in the SDK client factories.

Each inference client factory must pass the configured ``cogt.transport_max_retries`` explicitly
to the SDK client it builds, rather than inheriting the SDK's silent default. These tests patch
the SDK client constructor and assert the factory hands it the configured retry budget — they do
not exercise SDK retry over the network.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mistralai.utils import RetryConfig

from pipelex.providers.anthropic.anthropic_factory import AnthropicFactory
from pipelex.providers.gateway.gateway_completions_factory import GatewayCompletionsFactory
from pipelex.providers.gateway.gateway_responses_factory import GatewayResponsesFactory
from pipelex.providers.google.google_factory import GoogleFactory
from pipelex.providers.mistral.mistral_factory import MistralFactory
from pipelex.providers.openai.openai_client_factory import OpenAIClientFactory
from pipelex.providers.portkey.portkey_completions_factory import PortkeyCompletionsFactory
from pipelex.providers.portkey.portkey_responses_factory import PortkeyResponsesFactory

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _config_with(mocker: MockerFixture, transport_max_retries: int) -> object:
    config = mocker.MagicMock()
    config.inference.transport_max_retries = transport_max_retries
    return config


class TestTransportRetryWiring:
    """Every SDK client factory wires ``transport_max_retries`` from config into the client."""

    def test_anthropic_factory_passes_max_retries(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.providers.anthropic.anthropic_factory.get_config",
            return_value=_config_with(mocker, 5),
        )
        mock_client = mocker.patch("pipelex.providers.anthropic.anthropic_factory.AsyncAnthropic")
        model_handle = mocker.MagicMock()
        model_handle.sdk = "anthropic"

        AnthropicFactory.make_anthropic_client(model_handle=model_handle, backend=mocker.MagicMock())

        mock_client.assert_called_once()
        assert mock_client.call_args.kwargs["max_retries"] == 5

    def test_openai_factory_passes_max_retries(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.providers.openai.openai_client_factory.get_config",
            return_value=_config_with(mocker, 7),
        )
        mock_client = mocker.patch("openai.AsyncOpenAI")
        model_handle = mocker.MagicMock()
        model_handle.sdk = "openai"

        OpenAIClientFactory.make_openai_client(model_handle=model_handle, backend=mocker.MagicMock())

        mock_client.assert_called_once()
        assert mock_client.call_args.kwargs["max_retries"] == 7

    def test_mistral_factory_builds_retry_config_when_enabled(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.providers.mistral.mistral_factory.get_config",
            return_value=_config_with(mocker, 3),
        )
        mock_client = mocker.patch("pipelex.providers.mistral.mistral_factory.Mistral")

        MistralFactory.make_mistral_client(backend=mocker.MagicMock())

        mock_client.assert_called_once()
        retry_config = mock_client.call_args.kwargs["retry_config"]
        assert isinstance(retry_config, RetryConfig)
        assert retry_config.retry_connection_errors is True

    def test_mistral_factory_disables_retry_when_zero(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.providers.mistral.mistral_factory.get_config",
            return_value=_config_with(mocker, 0),
        )
        mock_client = mocker.patch("pipelex.providers.mistral.mistral_factory.Mistral")

        MistralFactory.make_mistral_client(backend=mocker.MagicMock())

        mock_client.assert_called_once()
        assert mock_client.call_args.kwargs["retry_config"] is None

    def test_google_factory_passes_retry_options(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.providers.google.google_factory.get_config",
            return_value=_config_with(mocker, 4),
        )
        mock_client = mocker.patch("pipelex.providers.google.google_factory.GoogleGenAiClient")

        GoogleFactory.make_google_client(backend=mocker.MagicMock())

        mock_client.assert_called_once()
        http_options = mock_client.call_args.kwargs["http_options"]
        assert http_options.retry_options is not None
        # HttpRetryOptions.attempts counts the original attempt, so it is transport_max_retries + 1.
        assert http_options.retry_options.attempts == 5

    def test_portkey_completions_factory_passes_max_retries(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.providers.portkey.portkey_completions_factory.get_config",
            return_value=_config_with(mocker, 6),
        )
        mocker.patch("pipelex.providers.portkey.portkey_completions_factory.PortkeyFactory.is_debug_enabled", return_value=False)
        mocker.patch("pipelex.providers.portkey.portkey_completions_factory.PortkeyFactory.get_endpoint", return_value="https://gateway.test")
        mocker.patch("pipelex.providers.portkey.portkey_completions_factory.PortkeyFactory.get_api_key", return_value="pk-test")
        mocker.patch("pipelex.providers.portkey.portkey_completions_factory.PortkeyOpenAISdkVariant.is_completions", return_value=True)
        mock_client = mocker.patch("openai.AsyncOpenAI")

        PortkeyCompletionsFactory.make_portkey_openai_client_for_completions(model_handle=mocker.MagicMock(), backend=mocker.MagicMock())

        mock_client.assert_called_once()
        assert mock_client.call_args.kwargs["max_retries"] == 6

    def test_portkey_responses_factory_passes_max_retries(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.providers.portkey.portkey_responses_factory.get_config",
            return_value=_config_with(mocker, 8),
        )
        mocker.patch("pipelex.providers.portkey.portkey_responses_factory.PortkeyFactory.is_debug_enabled", return_value=False)
        mocker.patch("pipelex.providers.portkey.portkey_responses_factory.PortkeyFactory.get_endpoint", return_value="https://gateway.test")
        mocker.patch("pipelex.providers.portkey.portkey_responses_factory.PortkeyFactory.get_api_key", return_value="pk-test")
        mocker.patch("pipelex.providers.portkey.portkey_responses_factory.PortkeyOpenAISdkVariant.is_responses", return_value=True)
        mock_client = mocker.patch("openai.AsyncOpenAI")

        PortkeyResponsesFactory.make_portkey_openai_client_for_responses(model_handle=mocker.MagicMock(), backend=mocker.MagicMock())

        mock_client.assert_called_once()
        assert mock_client.call_args.kwargs["max_retries"] == 8

    def test_gateway_completions_factory_passes_max_retries(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.providers.gateway.gateway_completions_factory.get_config",
            return_value=_config_with(mocker, 4),
        )
        mocker.patch("pipelex.providers.gateway.gateway_completions_factory.GatewayFactory.is_debug_enabled", return_value=False)
        mocker.patch("pipelex.providers.gateway.gateway_completions_factory.GatewayFactory.get_endpoint", return_value="https://gateway.test")
        mocker.patch("pipelex.providers.gateway.gateway_completions_factory.GatewayFactory.get_api_key", return_value="gw-test")
        mocker.patch("pipelex.providers.gateway.gateway_completions_factory.GatewayOpenAISdkVariant.is_completions", return_value=True)
        mock_client = mocker.patch("openai.AsyncOpenAI")

        GatewayCompletionsFactory.make_portkey_openai_client_for_completions(model_handle=mocker.MagicMock(), backend=mocker.MagicMock())

        mock_client.assert_called_once()
        assert mock_client.call_args.kwargs["max_retries"] == 4

    def test_gateway_responses_factory_passes_max_retries(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "pipelex.providers.gateway.gateway_responses_factory.get_config",
            return_value=_config_with(mocker, 9),
        )
        mocker.patch("pipelex.providers.gateway.gateway_responses_factory.GatewayFactory.is_debug_enabled", return_value=False)
        mocker.patch("pipelex.providers.gateway.gateway_responses_factory.GatewayFactory.get_endpoint", return_value="https://gateway.test")
        mocker.patch("pipelex.providers.gateway.gateway_responses_factory.GatewayFactory.get_api_key", return_value="gw-test")
        mocker.patch("pipelex.providers.gateway.gateway_responses_factory.GatewayOpenAISdkVariant.is_responses", return_value=True)
        mock_client = mocker.patch("openai.AsyncOpenAI")

        GatewayResponsesFactory.make_portkey_openai_client_for_responses(model_handle=mocker.MagicMock(), backend=mocker.MagicMock())

        mock_client.assert_called_once()
        assert mock_client.call_args.kwargs["max_retries"] == 9
