"""How the Anthropic SDK client authenticates, per backend.

The anthropic SDK carries its key in ``x-api-key``. That is right for Anthropic itself and for the
Anthropic-compatible vendors, and wrong for a backend that fronts the protocol behind a gateway
which authenticates on a header of its own — the Pipelex inference gateway reads
``x-portkey-api-key`` (or an ``Authorization`` bearer) and never looks at ``x-api-key``, so a key
left in the SDK's own slot reaches it as an anonymous request. A backend says which header carries
its key with the ``auth_header`` extra-config field; these tests pin both paths and the refusal.
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

_GATEWAY_AUTH_HEADER = "x-portkey-api-key"


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
            name="pig_anthropic",
            endpoint="http://localhost:8787/v1",
            api_key="pig-service-token",
            extra_config={"auth_header": _GATEWAY_AUTH_HEADER},
        )

        AnthropicFactory.make_anthropic_client(model_handle=_model_handle(), backend=backend)

        kwargs = mock_client.call_args.kwargs
        assert kwargs["default_headers"] == {_GATEWAY_AUTH_HEADER: "pig-service-token"}
        # The SDK refuses an empty api_key, so the slot holds a placeholder rather than the token.
        assert kwargs["api_key"] != "pig-service-token"
        assert kwargs["api_key"]
        assert kwargs["base_url"] == "http://localhost:8787/v1"

    def test_auth_header_without_a_key_is_refused(self, mocker: MockerFixture) -> None:
        _patch_config(mocker)
        mocker.patch("pipelex.providers.anthropic.anthropic_factory.AsyncAnthropic")
        backend = InferenceBackend(
            name="pig_anthropic",
            endpoint="http://localhost:8787/v1",
            api_key=None,
            extra_config={"auth_header": _GATEWAY_AUTH_HEADER},
        )

        with pytest.raises(AnthropicFactoryError, match="auth_header"):
            AnthropicFactory.make_anthropic_client(model_handle=_model_handle(), backend=backend)
