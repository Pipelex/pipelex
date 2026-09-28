from collections.abc import Mapping
from typing import Any

import httpx
from anthropic import DEFAULT_MAX_RETRIES, NOT_GIVEN, NotGiven
from anthropic.lib.bedrock import AsyncAnthropicBedrock

from pipelex.providers.anthropic.anthropic_exceptions import AnthropicFactoryError


class AsyncAnthropicBedrockSigV4(AsyncAnthropicBedrock):
    """A Bedrock client that always signs with SigV4 from the AWS keys it is given, whatever the environment says.

    `AsyncAnthropicBedrock` fills `api_key` from `AWS_BEARER_TOKEN_BEDROCK` whenever it is given none, unconditionally,
    and then refuses explicit AWS credentials beside it with a `ValueError`. Pipelex's `bedrock_access_variant` is its one
    statement of which Bedrock credentials to use, so under `aws_access` a token in the environment, typically set for
    another tool, must not decide anything. This class hands the SDK constructor only the region and the transport
    options, which never clash, then resets `api_key` to `None` and sets the credentials itself: the SDK's request hook
    signs with SigV4 whenever `api_key` is `None`, reading exactly these attributes.

    The SDK's `copy` (alias `with_options`) rebuilds the client through `self.__class__` with the stored credentials and
    `api_key=None`, so a copy takes the same path. Options that later SDK releases add to the constructor and pass through
    `copy`, such as `middleware` from anthropic 0.108, reach the parent unchanged through `**kwargs`. This couples to four
    public attributes of the SDK client and to the rule that `api_key is None` means SigV4; `test_anthropic_bedrock_auth.py`
    guards the coupling on the wire, so an SDK release that changes it fails there at the dependency bump.
    """

    def __init__(
        self,
        *,
        aws_access_key: str,
        aws_secret_key: str,
        aws_region: str,
        aws_session_token: str | None = None,
        api_key: str | None = None,
        base_url: str | httpx.URL | None = None,
        timeout: float | httpx.Timeout | NotGiven | None = NOT_GIVEN,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Mapping[str, str] | None = None,
        default_query: Mapping[str, object] | None = None,
        http_client: httpx.AsyncClient | None = None,
        **kwargs: Any,
    ) -> None:
        # The parameter exists only because the SDK's `copy` always passes one.
        if api_key is not None:
            msg = (
                "AsyncAnthropicBedrockSigV4 signs with AWS access keys and takes no api_key: "
                "a Bedrock bearer token belongs to the 'bedrock_token' access variant"
            )
            raise AnthropicFactoryError(msg)
        super().__init__(
            aws_region=aws_region,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            default_query=default_query,
            http_client=http_client,
            **kwargs,
        )
        # The parent has just filled api_key from AWS_BEARER_TOKEN_BEDROCK if it is set: None is what makes it sign with SigV4.
        self.api_key = None
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.aws_session_token = aws_session_token
