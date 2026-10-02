"""Under `bedrock_access_variant = "aws_access"`, the configured AWS keys sign every `bedrock_anthropic` request, whatever the
environment says.

The anthropic SDK's Bedrock client reads `AWS_BEARER_TOKEN_BEDROCK` whenever it is given no `api_key`, then refuses explicit AWS
credentials beside it with a raw `ValueError`. That variable is the standard name for a Bedrock API key, which other AWS tooling
reads, so a developer who keeps one in a shell profile could not run a single `bedrock_anthropic` model under pipelex's default
configuration. `[runtime.aws]` is pipelex's one statement of where Bedrock credentials come from, so the configured variant wins:
the factory builds a SigV4-only subclass of the SDK client which drops the token the SDK picked up.

That subclass relies on the SDK's rule that an `api_key` of `None` means SigV4 signing, so these tests check the wire rather than
the attributes: a request sent through an `httpx.MockTransport` with the variable set must carry a SigV4 `Authorization` header
naming the configured key id. An SDK release that changes the rule turns them red at the dependency bump.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from anthropic.lib.bedrock import AsyncAnthropicBedrock

from pipelex.plugins.model_handle import ModelHandle
from pipelex.providers.anthropic.anthropic_bedrock_sigv4 import AsyncAnthropicBedrockSigV4
from pipelex.providers.anthropic.anthropic_exceptions import AnthropicFactoryError
from pipelex.providers.anthropic.anthropic_factory import AnthropicFactory
from pipelex.tools.aws.aws_config import (
    AWS_ACCESS_KEY_ID_VAR_NAME,
    AWS_REGION_VAR_NAME,
    AWS_SECRET_ACCESS_KEY_VAR_NAME,
    BEDROCK_TOKEN_VAR_NAME,
    AwsConfig,
    AwsKeyMethod,
    BedrockAccessVariant,
)
from pipelex.tools.aws.exceptions import AwsCredentialsError
from pipelex.tools.secrets.exceptions import SecretNotFoundError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_KEY_ID = "AKIAPIPELEXTESTKEY01"
_SECRET_KEY = "pipelex-test-secret-access-key"
_REGION = "eu-west-3"
_ENV_BEARER_TOKEN = "bedrock-bearer-token-from-the-shell"
_SIGV4_PREFIX = f"AWS4-HMAC-SHA256 Credential={_KEY_ID}/"
_MODEL = "anthropic.claude-haiku-4-5-20251001-v1:0"
_MESSAGE_RESPONSE: dict[str, Any] = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": _MODEL,
    "content": [{"type": "text", "text": "ok"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 1, "output_tokens": 1},
}


def _model_handle() -> ModelHandle:
    return ModelHandle(sdk="bedrock_anthropic", backend="bedrock")


def _patch_config(
    mocker: MockerFixture,
    *,
    bedrock_access_variant: BedrockAccessVariant,
    api_key_method: AwsKeyMethod = AwsKeyMethod.ENV,
) -> None:
    config = mocker.MagicMock()
    config.inference.transport_max_retries = 0
    config.runtime.aws = AwsConfig(api_key_method=api_key_method, bedrock_access_variant=bedrock_access_variant)
    mocker.patch("pipelex.providers.anthropic.anthropic_factory.get_config", return_value=config)


def _set_access_keys_in_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AWS_ACCESS_KEY_ID_VAR_NAME, _KEY_ID)
    monkeypatch.setenv(AWS_SECRET_ACCESS_KEY_VAR_NAME, _SECRET_KEY)
    monkeypatch.setenv(AWS_REGION_VAR_NAME, _REGION)


def _recording_transport(seen_authorizations: list[str]) -> httpx.MockTransport:
    def _handler(request: httpx.Request) -> httpx.Response:
        seen_authorizations.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json=_MESSAGE_RESPONSE)

    return httpx.MockTransport(_handler)


async def _send_one_message(client: AsyncAnthropicBedrock) -> None:
    await client.messages.create(model=_MODEL, max_tokens=8, messages=[{"role": "user", "content": "ping"}])


class TestAnthropicBedrockAuth:
    @pytest.mark.asyncio
    async def test_sigv4_client_signs_with_the_configured_keys_despite_the_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With the bearer token in the environment, the request still carries a SigV4 signature from the configured key id."""
        monkeypatch.setenv(BEDROCK_TOKEN_VAR_NAME, _ENV_BEARER_TOKEN)
        seen_authorizations: list[str] = []
        async with httpx.AsyncClient(transport=_recording_transport(seen_authorizations)) as http_client:
            client = AsyncAnthropicBedrockSigV4(
                aws_access_key=_KEY_ID,
                aws_secret_key=_SECRET_KEY,
                aws_region=_REGION,
                max_retries=0,
                http_client=http_client,
            )
            await _send_one_message(client)

        assert len(seen_authorizations) == 1
        assert seen_authorizations[0].startswith(_SIGV4_PREFIX)
        assert not seen_authorizations[0].startswith("Bearer")

    @pytest.mark.asyncio
    async def test_with_options_copy_signs_the_same_way(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The SDK's `copy` rebuilds the client through its class, re-reading the environment, and must sign with SigV4 all the same."""
        monkeypatch.setenv(BEDROCK_TOKEN_VAR_NAME, _ENV_BEARER_TOKEN)
        client = AsyncAnthropicBedrockSigV4(aws_access_key=_KEY_ID, aws_secret_key=_SECRET_KEY, aws_region=_REGION, max_retries=0)
        seen_authorizations: list[str] = []
        # The SDK's copy does not carry a custom http_client over, so the mock transport is passed again.
        async with httpx.AsyncClient(transport=_recording_transport(seen_authorizations)) as http_client:
            copied_client = client.with_options(http_client=http_client, timeout=30)
            await _send_one_message(copied_client)

        assert isinstance(copied_client, AsyncAnthropicBedrockSigV4)
        assert copied_client.api_key is None
        assert len(seen_authorizations) == 1
        assert seen_authorizations[0].startswith(_SIGV4_PREFIX)

    def test_copy_forwards_the_options_the_subclass_does_not_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Later SDK releases pass new options through `copy` (`middleware` from 0.108): the subclass forwards what it does not name."""
        monkeypatch.setenv(BEDROCK_TOKEN_VAR_NAME, _ENV_BEARER_TOKEN)
        client = AsyncAnthropicBedrockSigV4(aws_access_key=_KEY_ID, aws_secret_key=_SECRET_KEY, aws_region=_REGION, max_retries=0)

        copied_client = client.copy(_extra_kwargs={"_strict_response_validation": True})

        assert isinstance(copied_client, AsyncAnthropicBedrockSigV4)
        assert copied_client._strict_response_validation is True  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
        assert copied_client.api_key is None
        assert copied_client.aws_access_key == _KEY_ID

    @pytest.mark.parametrize("token_in_env", [True, False], ids=["token_in_env", "no_token"])
    def test_factory_builds_the_sigv4_client_under_aws_access(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        token_in_env: bool,
    ) -> None:
        """Under `aws_access` the factory builds the SigV4 client from the configured keys, whether or not the token is set."""
        _patch_config(mocker, bedrock_access_variant=BedrockAccessVariant.AWS_ACCESS)
        _set_access_keys_in_env(monkeypatch)
        if token_in_env:
            monkeypatch.setenv(BEDROCK_TOKEN_VAR_NAME, _ENV_BEARER_TOKEN)
        else:
            monkeypatch.delenv(BEDROCK_TOKEN_VAR_NAME, raising=False)

        client = AnthropicFactory.make_anthropic_client(model_handle=_model_handle(), backend=mocker.MagicMock())

        assert isinstance(client, AsyncAnthropicBedrockSigV4)
        assert client.api_key is None
        assert client.aws_access_key == _KEY_ID
        assert client.aws_secret_key == _SECRET_KEY
        assert client.aws_region == _REGION
        assert client.max_retries == 0

    @pytest.mark.asyncio
    async def test_bedrock_token_variant_sends_the_token_as_bearer(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """Under `bedrock_token` the factory keeps the plain SDK client, which authenticates with the token as a bearer."""
        _patch_config(mocker, bedrock_access_variant=BedrockAccessVariant.BEDROCK_TOKEN)
        monkeypatch.setenv(BEDROCK_TOKEN_VAR_NAME, _ENV_BEARER_TOKEN)

        client = AnthropicFactory.make_anthropic_client(model_handle=_model_handle(), backend=mocker.MagicMock())

        assert isinstance(client, AsyncAnthropicBedrock)
        assert not isinstance(client, AsyncAnthropicBedrockSigV4)
        assert client.api_key == _ENV_BEARER_TOKEN
        seen_authorizations: list[str] = []
        async with httpx.AsyncClient(transport=_recording_transport(seen_authorizations)) as http_client:
            await _send_one_message(client.with_options(http_client=http_client))

        assert seen_authorizations == [f"Bearer {_ENV_BEARER_TOKEN}"]

    @pytest.mark.parametrize("token_in_env", [True, False], ids=["token_in_env", "no_token"])
    @pytest.mark.parametrize(
        ("api_key_method", "expects_secrets_provider_note"),
        [
            pytest.param(AwsKeyMethod.ENV, False, id="env"),
            pytest.param(AwsKeyMethod.SECRET_PROVIDER, True, id="secret_provider"),
        ],
    )
    def test_missing_keys_hint_at_the_token_only_when_it_is_set(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        api_key_method: AwsKeyMethod,
        expects_secrets_provider_note: bool,
        token_in_env: bool,
    ) -> None:
        """Missing access keys raise `AwsCredentialsError`, naming the bearer token and the `bedrock_token` variant only when it is set."""
        _patch_config(mocker, bedrock_access_variant=BedrockAccessVariant.AWS_ACCESS, api_key_method=api_key_method)
        for var_name in (AWS_ACCESS_KEY_ID_VAR_NAME, AWS_SECRET_ACCESS_KEY_VAR_NAME, AWS_REGION_VAR_NAME):
            monkeypatch.delenv(var_name, raising=False)
        # A secrets provider that holds none of the keys, as a vault missing them would.
        mocker.patch("pipelex.tools.aws.aws_config.get_secret", side_effect=SecretNotFoundError("Secret not found"))
        if token_in_env:
            monkeypatch.setenv(BEDROCK_TOKEN_VAR_NAME, _ENV_BEARER_TOKEN)
        else:
            monkeypatch.delenv(BEDROCK_TOKEN_VAR_NAME, raising=False)

        with pytest.raises(AwsCredentialsError) as exc_info:
            AnthropicFactory.make_anthropic_client(model_handle=_model_handle(), backend=mocker.MagicMock())

        message = str(exc_info.value)
        if token_in_env:
            cause = exc_info.value.__cause__
            assert isinstance(cause, AwsCredentialsError)
            assert message.startswith(f"{str(cause).rstrip('.')}. The environment sets {BEDROCK_TOKEN_VAR_NAME}")
            assert BEDROCK_TOKEN_VAR_NAME in message
            assert f'bedrock_access_variant = "{BedrockAccessVariant.BEDROCK_TOKEN}"' in message
            assert _ENV_BEARER_TOKEN not in message
            # Under secret_provider, the bedrock_token variant reads the token from the secrets provider, and the hint says so.
            assert ("from the secrets provider" in message) == expects_secrets_provider_note
        else:
            assert BEDROCK_TOKEN_VAR_NAME not in message
            assert BedrockAccessVariant.BEDROCK_TOKEN not in message

    def test_sigv4_client_refuses_an_api_key(self) -> None:
        """The SigV4 client exists to sign with the access keys, so handing it a token is a mistake it refuses."""
        with pytest.raises(AnthropicFactoryError, match="api_key"):
            AsyncAnthropicBedrockSigV4(aws_access_key=_KEY_ID, aws_secret_key=_SECRET_KEY, aws_region=_REGION, api_key="some-token")
