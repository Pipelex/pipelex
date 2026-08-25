"""What each manifold client is handed at construction.

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
from pipelex.providers.manifold.manifold_completions_factory import ManifoldCompletionsFactory
from pipelex.providers.manifold.manifold_constants import ManifoldSdk
from pipelex.providers.manifold.manifold_exceptions import ManifoldFactoryError
from pipelex.providers.manifold.manifold_factory import ManifoldFactory
from pipelex.providers.manifold.manifold_responses_factory import ManifoldResponsesFactory

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pytest_mock import MockerFixture

_ORIGIN = "https://manifold.example.com"
_TOKEN = "manifold-service-token"
_AUTH_HEADER = "x-portkey-api-key"

# Anything that would tell the service who should serve the model. None of it belongs on this path:
# the model id in the body is the whole of the routing decision, and the gateway refuses a client
# that tries to make it (`pig-03`).
_ROUTING_MARKERS = ("x-portkey-config", "x-portkey-provider", "x-portkey-virtual-key", "x-portkey-custom-host")


def _backend() -> InferenceBackend:
    return InferenceBackend(name="pipelex_manifold", endpoint=_ORIGIN, api_key=_TOKEN)


def _handle(sdk: ManifoldSdk) -> ModelHandle:
    return ModelHandle(sdk=str(sdk), backend="pipelex_manifold")


def _patch_config(mocker: MockerFixture, module: str) -> None:
    config = mocker.MagicMock()
    config.inference.transport_max_retries = 3
    mocker.patch(f"{module}.get_config", return_value=config)


def _assert_no_routing(kwargs: Mapping[str, Any]) -> None:
    rendered = str(kwargs).lower()
    for marker in _ROUTING_MARKERS:
        assert marker not in rendered, f"the manifold client was handed a routing marker: {marker}"


class TestManifoldCompletionsClient:
    def test_the_client_gets_the_origin_plus_v1_and_the_token_in_the_service_header(self, mocker: MockerFixture) -> None:
        _patch_config(mocker, "pipelex.providers.manifold.manifold_completions_factory")
        mock_openai = mocker.patch("openai.AsyncOpenAI")

        ManifoldCompletionsFactory.make_openai_client_for_completions(_handle(ManifoldSdk.COMPLETIONS), backend=_backend())

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
        _patch_config(mocker, "pipelex.providers.manifold.manifold_completions_factory")
        mocker.patch("openai.AsyncOpenAI")

        with pytest.raises(ManifoldFactoryError):
            ManifoldCompletionsFactory.make_openai_client_for_completions(_handle(ManifoldSdk.RESPONSES), backend=_backend())


class TestManifoldResponsesClient:
    def test_the_client_gets_the_origin_plus_v1_and_the_token_in_the_service_header(self, mocker: MockerFixture) -> None:
        _patch_config(mocker, "pipelex.providers.manifold.manifold_responses_factory")
        mock_openai = mocker.patch("openai.AsyncOpenAI")

        ManifoldResponsesFactory.make_openai_client_for_responses(_handle(ManifoldSdk.RESPONSES), backend=_backend())

        kwargs = mock_openai.call_args.kwargs
        assert kwargs["base_url"] == f"{_ORIGIN}/v1"
        assert kwargs["default_headers"] == {_AUTH_HEADER: _TOKEN}
        assert kwargs["api_key"] != _TOKEN
        _assert_no_routing(kwargs)

    def test_a_handle_from_another_sdk_set_is_refused(self, mocker: MockerFixture) -> None:
        _patch_config(mocker, "pipelex.providers.manifold.manifold_responses_factory")
        mocker.patch("openai.AsyncOpenAI")

        with pytest.raises(ManifoldFactoryError):
            ManifoldResponsesFactory.make_openai_client_for_responses(_handle(ManifoldSdk.COMPLETIONS), backend=_backend())


class TestManifoldImageClient:
    def test_the_vendor_client_is_built_under_the_same_endpoint_rule(self, mocker: MockerFixture) -> None:
        """`AsyncPortkey` is a beta-only dependency of the image path, and it obeys the same rule.

        The vendor SDK's own `base_url` default is Portkey's cloud, so the value passed here is the
        whole of what keeps this client pointed at our service.
        """
        mock_portkey = mocker.patch("portkey_ai.AsyncPortkey")

        ManifoldFactory.make_portkey_client(_backend())

        kwargs = mock_portkey.call_args.kwargs
        assert kwargs["base_url"] == f"{_ORIGIN}/v1"
        assert kwargs["api_key"] == _TOKEN
        _assert_no_routing(kwargs)

    def test_debug_is_read_from_the_backend_and_from_nothing_else(self, mocker: MockerFixture) -> None:
        """One configuration block must not govern two services.

        The Portkey-path sibling routes this through the telemetry manager's `pipelex_gateway.portkey`
        knobs; reading those here would make a change meant for the cloud path silently alter the
        manifold one.
        """
        mocker.patch("portkey_ai.AsyncPortkey")
        backend = InferenceBackend(name="pipelex_manifold", endpoint=_ORIGIN, api_key=_TOKEN, extra_config={"debug": True})

        assert ManifoldFactory.is_debug_enabled(backend) is True
        assert ManifoldFactory.is_debug_enabled(_backend()) is False
