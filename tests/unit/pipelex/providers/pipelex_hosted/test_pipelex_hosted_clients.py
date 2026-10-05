"""What each hosted client is handed at construction.

Three SDKs sit under this package and they do not agree about `base_url`: `AsyncOpenAI` and
`AsyncPortkey` both expect the version segment in it (their own defaults are
`https://api.openai.com/v1` and `https://api.portkey.ai/v1`), while `AsyncAnthropic` defaults to
`https://api.anthropic.com` and appends `/v1/messages` itself. The origin rule composes with all
three only because each factory appends what its SDK expects — so these tests read the arguments the
factory actually passed rather than trusting that it did.

The second property pinned here is negative and matters more: **nothing about routing is sent.** The
token travels in the service's own header, the OpenAI `Authorization` slot holds a placeholder the
gateway never reads, and no config id or provider name appears anywhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.plugins.model_handle import ModelHandle
from pipelex.providers.pipelex_hosted.pipelex_hosted_completions_factory import PipelexHostedCompletionsFactory
from pipelex.providers.pipelex_hosted.pipelex_hosted_constants import PipelexHostedSdk
from pipelex.providers.pipelex_hosted.pipelex_hosted_exceptions import PipelexHostedFactoryError
from pipelex.providers.pipelex_hosted.pipelex_hosted_factory import PipelexHostedFactory
from pipelex.providers.pipelex_hosted.pipelex_hosted_responses_factory import PipelexHostedResponsesFactory

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pytest_mock import MockerFixture

_ORIGIN = "https://pipelex_hosted.example.com"
_TOKEN = "hosted-service-token"
_AUTH_HEADER = "x-pipelex-api-key"

# Anything that would tell the service who should serve the model. None of it belongs on this path:
# the model id in the body is the whole of the routing decision, and the gateway refuses a client
# that tries to make it (`pig-03`).
_ROUTING_MARKERS = ("x-portkey-config", "x-portkey-provider", "x-portkey-virtual-key", "x-portkey-custom-host")


def _backend() -> InferenceBackend:
    return InferenceBackend(name="pipelex_hosted", endpoint=_ORIGIN, api_key=_TOKEN)


def _handle(sdk: PipelexHostedSdk) -> ModelHandle:
    return ModelHandle(sdk=str(sdk), backend="pipelex_hosted")


def _patch_config(mocker: MockerFixture, module: str) -> None:
    config = mocker.MagicMock()
    config.inference.transport_max_retries = 3
    mocker.patch(f"{module}.get_config", return_value=config)


def _assert_no_routing(kwargs: Mapping[str, Any]) -> None:
    rendered = str(kwargs).lower()
    for marker in _ROUTING_MARKERS:
        assert marker not in rendered, f"the hosted client was handed a routing marker: {marker}"


class TestPipelexHostedCompletionsClient:
    def test_the_client_gets_the_origin_plus_v1_and_the_token_in_the_service_header(self, mocker: MockerFixture) -> None:
        _patch_config(mocker, "pipelex.providers.pipelex_hosted.pipelex_hosted_completions_factory")
        mock_openai = mocker.patch("openai.AsyncOpenAI")

        PipelexHostedCompletionsFactory.make_openai_client_for_completions(_handle(PipelexHostedSdk.COMPLETIONS), backend=_backend())

        kwargs = mock_openai.call_args.kwargs
        assert kwargs["base_url"] == f"{_ORIGIN}/v1"
        assert kwargs["default_headers"] == {_AUTH_HEADER: _TOKEN}
        assert kwargs["max_retries"] == 3
        # The SDK has refused an empty api_key since 2.34.0, so the slot holds a placeholder rather
        # than the token — sending the token twice would put it somewhere the gateway does not read.
        assert kwargs["api_key"] != _TOKEN
        assert kwargs["api_key"]
        _assert_no_routing(kwargs)

    def test_a_handle_from_another_sdk_set_is_refused(self, mocker: MockerFixture) -> None:
        _patch_config(mocker, "pipelex.providers.pipelex_hosted.pipelex_hosted_completions_factory")
        mocker.patch("openai.AsyncOpenAI")

        with pytest.raises(PipelexHostedFactoryError):
            PipelexHostedCompletionsFactory.make_openai_client_for_completions(_handle(PipelexHostedSdk.RESPONSES), backend=_backend())


class TestPipelexHostedResponsesClient:
    def test_the_client_gets_the_origin_plus_v1_and_the_token_in_the_service_header(self, mocker: MockerFixture) -> None:
        _patch_config(mocker, "pipelex.providers.pipelex_hosted.pipelex_hosted_responses_factory")
        mock_openai = mocker.patch("openai.AsyncOpenAI")

        PipelexHostedResponsesFactory.make_openai_client_for_responses(_handle(PipelexHostedSdk.RESPONSES), backend=_backend())

        kwargs = mock_openai.call_args.kwargs
        assert kwargs["base_url"] == f"{_ORIGIN}/v1"
        assert kwargs["default_headers"] == {_AUTH_HEADER: _TOKEN}
        assert kwargs["api_key"] != _TOKEN
        _assert_no_routing(kwargs)

    def test_a_handle_from_another_sdk_set_is_refused(self, mocker: MockerFixture) -> None:
        _patch_config(mocker, "pipelex.providers.pipelex_hosted.pipelex_hosted_responses_factory")
        mocker.patch("openai.AsyncOpenAI")

        with pytest.raises(PipelexHostedFactoryError):
            PipelexHostedResponsesFactory.make_openai_client_for_responses(_handle(PipelexHostedSdk.COMPLETIONS), backend=_backend())


class TestPipelexHostedImageClient:
    def test_the_vendor_client_is_built_under_the_same_endpoint_rule(self, mocker: MockerFixture) -> None:
        """`AsyncPortkey` is a beta-only dependency of the image path, and it obeys the same rule.

        The vendor SDK's own `base_url` default is Portkey's cloud, so the value passed here is the
        whole of what keeps this client pointed at our service.
        """
        mock_portkey = mocker.patch("portkey_ai.AsyncPortkey")

        PipelexHostedFactory.make_portkey_client(_backend())

        kwargs = mock_portkey.call_args.kwargs
        assert kwargs["base_url"] == f"{_ORIGIN}/v1"
        assert kwargs["api_key"] == _TOKEN
        _assert_no_routing(kwargs)

    def test_debug_is_read_from_the_backend_and_from_nothing_else(self, mocker: MockerFixture) -> None:
        """One configuration block must not govern two services.

        The Portkey-path sibling routes this through the telemetry manager's Portkey-path
        knobs; reading those here would make a change meant for the cloud path silently alter the
        hosted one.
        """
        mocker.patch("portkey_ai.AsyncPortkey")
        backend = InferenceBackend(name="pipelex_hosted", endpoint=_ORIGIN, api_key=_TOKEN, extra_config={"debug": True})

        assert PipelexHostedFactory.is_debug_enabled(backend) is True
        assert PipelexHostedFactory.is_debug_enabled(_backend()) is False
