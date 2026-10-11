"""The one request a sender makes: a batch of events posted to PostHog's capture API, or to a loopback override.

`POST <origin>/batch/` with `{"api_key": <project token>, "batch": [...]}` and nothing else: no SDK, so no library
property, no `sent_at` and no feature of a client this sender would then have to turn off. Redirects are refused, so a
batch can never be carried anywhere but the origin it was addressed to, and a loopback origin is reached without a proxy.

Standard library only, for the reason `usage_stats_contract` gives.
"""

import http.client
import json
import urllib.error
import urllib.request
from enum import StrEnum
from typing import Any

from typing_extensions import override

from pipelex.system.usage_stats.usage_stats_contract import BATCH_PATH, PERMANENT_REFUSAL_STATUSES, PROJECT_TOKEN
from pipelex.system.usage_stats.usage_stats_environment import is_loopback_origin

#: Below this many seconds left in a budget, a sender does not start a request it could not finish.
MINIMUM_REQUEST_SECONDS = 0.05


class PostVerdict(StrEnum):
    """What a sender does with what it posted, by PostHog's answer."""

    ACCEPTED = "accepted"
    REFUSED = "refused"
    RETRY = "retry"

    @property
    def is_final(self) -> bool:
        """Whether the events are done with: accepted, or refused for good so a resend would be refused again."""
        match self:
            case PostVerdict.ACCEPTED | PostVerdict.REFUSED:
                return True
            case PostVerdict.RETRY:
                return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    @override
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        return None


def verdict_for_status(*, status: int) -> PostVerdict:
    if 200 <= status < 300:
        return PostVerdict.ACCEPTED
    if status in PERMANENT_REFUSAL_STATUSES:
        return PostVerdict.REFUSED
    return PostVerdict.RETRY


def post_batch(*, origin: str, events: list[dict[str, Any]], timeout_seconds: float) -> PostVerdict:
    """Post `events` in one request that may take at most `timeout_seconds`; any failure to get an answer is `RETRY`."""
    if timeout_seconds < MINIMUM_REQUEST_SECONDS:
        return PostVerdict.RETRY
    body = json.dumps({"api_key": PROJECT_TOKEN, "batch": events}).encode("utf-8")
    request = urllib.request.Request(  # ruff: ignore[suspicious-url-open-usage] — the origin is PostHog's capture host or a loopback override, both checked
        url=f"{origin.rstrip('/')}{BATCH_PATH}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    handlers: list[urllib.request.BaseHandler] = [_NoRedirect()]
    if is_loopback_origin(origin=origin):
        handlers.append(urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status: int = response.status
    except urllib.error.HTTPError as http_error:
        return verdict_for_status(status=http_error.code)
    except (OSError, http.client.HTTPException, ValueError):
        # No answer at all: a network failure, a timeout, a connection closed mid-answer or an origin the opener refused.
        return PostVerdict.RETRY
    return verdict_for_status(status=status)
