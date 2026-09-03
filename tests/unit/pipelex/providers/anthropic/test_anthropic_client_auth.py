"""How the Anthropic SDK client authenticates, per backend.

The anthropic SDK carries its key in `x-api-key`. That is right for Anthropic itself and for the
Anthropic-compatible vendors, and wrong for a backend that fronts the protocol behind a gateway
which authenticates on a header of its own — the Pipelex Manifold service reads `x-pipelex-api-key`
(or an `Authorization` bearer) and never looks at `x-api-key`, so a key left in the SDK's own slot
reaches it as an anonymous request. A backend says which header carries its key with the
`auth_header` extra-config field; these tests pin both paths and the refusal.

This lives in `providers/anthropic/` rather than in the manifold package deliberately: the driver is
shared with the plain BYOK Anthropic backend and outlives the Portkey retirement. The gate is the
backend's own declaration, so a BYOK backend takes the unchanged path.

**The `base_url` here is the origin with no `/v1`, and that is the whole endpoint rule in one
assertion.** `AsyncAnthropic` defaults to `https://api.anthropic.com` and appends `/v1/messages`
itself, unlike the OpenAI and Portkey clients which expect the version segment in `base_url`. A
`/v1`-suffixed endpoint here produces `POST /v1/v1/messages`, which a gateway forwards and a
provider answers with a 200-shaped failure — the class of bug that cost spike 5 a day.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.plugins.model_handle import ModelHandle
from pipelex.providers.anthropic.anthropic_exceptions import AnthropicFactoryError
from pipelex.providers.anthropic.anthropic_factory import AnthropicFactory

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_MANIFOLD_AUTH_HEADER = "x-pipelex-api-key"
_MANIFOLD_ORIGIN = "https://manifold.example.com"


def _model_handle() -> ModelHandle:
    return ModelHandle(sdk="anthropic", backend="test_backend")


def _patch_config(mocker: MockerFixture) -> None:
    config = mocker.MagicMock()
    config.inference.transport_max_retries = 2
    mocker.patch("pipelex.providers.anthropic.anthropic_factory.get_config", return_value=config)


class TestAnthropicClientAuth:
    def test_plain_backend_keeps_the_key_in_the_sdk_slot(self, mocker: MockerFixture) -> None:
        _patch_config(mocker)
        mock_client = mocker.patch("pipelex.providers.anthropic.anthropic_factory.AsyncAnthropic")
        backend = InferenceBackend(name="anthropic", endpoint=None, api_key="sk-ant-test")

        AnthropicFactory.make_anthropic_client(model_handle=_model_handle(), backend=backend)

        kwargs = mock_client.call_args.kwargs
        assert kwargs["api_key"] == "sk-ant-test"
        assert "default_headers" not in kwargs

    def test_auth_header_backend_moves_the_key_into_that_header(self, mocker: MockerFixture) -> None:
        _patch_config(mocker)
        mock_client = mocker.patch("pipelex.providers.anthropic.anthropic_factory.AsyncAnthropic")
        backend = InferenceBackend(
            name="pipelex_manifold",
            endpoint=_MANIFOLD_ORIGIN,
            api_key="manifold-service-token",
            extra_config={"auth_header": _MANIFOLD_AUTH_HEADER},
        )

        AnthropicFactory.make_anthropic_client(model_handle=_model_handle(), backend=backend)

        kwargs = mock_client.call_args.kwargs
        assert kwargs["default_headers"] == {_MANIFOLD_AUTH_HEADER: "manifold-service-token"}
        # The SDK refuses an empty api_key, so the slot holds a placeholder rather than the token.
        assert kwargs["api_key"] != "manifold-service-token"
        assert kwargs["api_key"]
        # The origin, not the origin plus `/v1`: this SDK appends its own `/v1/messages`.
        assert kwargs["base_url"] == _MANIFOLD_ORIGIN

    def test_auth_header_without_a_key_is_refused(self, mocker: MockerFixture) -> None:
        _patch_config(mocker)
        mocker.patch("pipelex.providers.anthropic.anthropic_factory.AsyncAnthropic")
        backend = InferenceBackend(
            name="pipelex_manifold",
            endpoint=_MANIFOLD_ORIGIN,
            api_key=None,
            extra_config={"auth_header": _MANIFOLD_AUTH_HEADER},
        )

        with pytest.raises(AnthropicFactoryError, match="auth_header"):
            AnthropicFactory.make_anthropic_client(model_handle=_model_handle(), backend=backend)
