"""Whether a Pipelex API key looks like one, and whether the hosted API accepts it.

`pipelex login` checks a key before it saves it, and `pipelex init` reads whether one is already set, so both go
through here: the format check needs no network, and the hosted check asks the hosted API who the key belongs to
(`GET /v1/me`) through the one client factory. No CLI import, so either CLI can use it.
"""

import asyncio
import re
from enum import StrEnum
from typing import NamedTuple

from mthds.protocol.exceptions import PipelineRequestError
from pipelex_sdk.client import PipelexAPIClient
from pipelex_sdk.errors import ApiResponseError, ApiUnreachableError
from pipelex_sdk.product_models import UserProfile

from pipelex.hosted.client_factory import make_hosted_client, redact_url_for_display
from pipelex.hosted.exceptions import HostedBaseUrlError

#: Every Pipelex API key starts with this.
PIPELEX_API_KEY_PREFIX = "plx_sk_"
# The prefix, then URL-safe characters only: a key is written unquoted to a `.env` file, so a character a `.env`
# parser reads as a quote, a comment or a separator must never be part of one.
_PIPELEX_API_KEY_PATTERN = re.compile(rf"{PIPELEX_API_KEY_PREFIX}[A-Za-z0-9._~-]+")
#: The statuses by which the hosted API says the key itself is refused.
API_KEY_REFUSAL_STATUSES: frozenset[int] = frozenset({401, 403})


def is_well_formed_pipelex_api_key(*, api_key: str) -> bool:
    """Whether the value has the shape of a Pipelex API key: `plx_sk_` followed by URL-safe characters."""
    return _PIPELEX_API_KEY_PATTERN.fullmatch(api_key) is not None


class ApiKeyVerdict(StrEnum):
    """What the hosted API said of a key."""

    ACCEPTED = "accepted"
    REFUSED = "refused"
    UNCHECKED = "unchecked"


class ApiKeyCheck(NamedTuple):
    """The outcome of asking the hosted API who a key belongs to.

    `http_status` is the refusal's status (401 or 403) when the key was refused, and the status of an answer that
    neither accepted nor refused it. `reason` says why the key could not be checked, for a warning; it never quotes
    the key. `account_email` names the account an accepted key belongs to, when the hosted API said.
    """

    verdict: ApiKeyVerdict
    base_url: str
    http_status: int | None = None
    reason: str | None = None
    account_email: str | None = None


async def _get_profile(*, client: PipelexAPIClient) -> UserProfile:
    async with client:
        return await client.get_me()


def check_pipelex_api_key(*, api_key: str) -> ApiKeyCheck:
    """Ask the hosted API whether it accepts this key, with `GET /v1/me`.

    The hosted API is the one `PIPELEX_BASE_URL` names, else `https://api.pipelex.com`. Only a 401 or a 403 refuses
    the key; any other failure (the network, a bad base URL, another status, an answer that is not a profile) leaves it
    unchecked, with the reason.

    Args:
        api_key: The key to check, sent as the bearer token of this one request.

    Returns:
        The verdict, the base URL asked, and the status, the reason or the account.
    """
    try:
        client = make_hosted_client(api_key=api_key)
    except HostedBaseUrlError as exc:
        return ApiKeyCheck(verdict=ApiKeyVerdict.UNCHECKED, base_url="", reason=exc.message)
    base_url = client.base_url
    try:
        profile = asyncio.run(_get_profile(client=client))
    except ApiResponseError as exc:
        if exc.status in API_KEY_REFUSAL_STATUSES:
            return ApiKeyCheck(verdict=ApiKeyVerdict.REFUSED, base_url=base_url, http_status=exc.status)
        return ApiKeyCheck(
            verdict=ApiKeyVerdict.UNCHECKED,
            base_url=base_url,
            http_status=exc.status,
            reason=f"the hosted API at {redact_url_for_display(url=base_url)} answered HTTP {exc.status}",
        )
    except ApiUnreachableError:
        return ApiKeyCheck(
            verdict=ApiKeyVerdict.UNCHECKED,
            base_url=base_url,
            reason=f"the hosted API at {redact_url_for_display(url=base_url)} could not be reached",
        )
    except (PipelineRequestError, ValueError) as exc:
        # A non-2xx answer the SDK maps to its plainer error, or a 2xx body that is not JSON or not a profile (a JSON
        # decoding error and a pydantic validation error are both `ValueError`s): whatever answered is not the hosted API.
        return ApiKeyCheck(
            verdict=ApiKeyVerdict.UNCHECKED,
            base_url=base_url,
            reason=f"the hosted API at {redact_url_for_display(url=base_url)} did not answer with an account ({type(exc).__name__})",
        )
    return ApiKeyCheck(verdict=ApiKeyVerdict.ACCEPTED, base_url=base_url, account_email=profile.email)
