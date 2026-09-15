"""The submission-time reachability probe over a run's remote inputs.

A caller who hands a method a dead link hears about it before the run spends anything.
The probe runs once, over the inputs the caller gave, in the process that accepted the
request — never in workflow code, where a network wait trips an orchestrator's deadlock
detector, and never over values a pipe produces mid-run, which their consumer fetches
inside its own activity.

It is a ping, not a download: a ``HEAD``, then a one-byte ranged ``GET`` for the hosts
that reject ``HEAD``, every URL at once, one short budget each. And it is deliberately
permissive, because a probe cannot tell a blocked page from a dead one: a link is
refused only on an unambiguous signal — the host does not resolve, refuses the
connection, or answers ``404``/``410``. Everything else (``401``/``403``/``429`` from a
bot wall, a slow host, any other status) passes with a warning, and the real fetch
decides.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import TYPE_CHECKING, NamedTuple, cast

import httpx
from pydantic import BaseModel, ConfigDict

from pipelex import log
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.tools.misc.http_utils import get_user_agent
from pipelex.tools.network.exceptions import SsrfBlockedError
from pipelex.tools.network.ssrf_guard import SsrfGuardedTransport

if TYPE_CHECKING:
    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.core.stuffs.stuff_content import StuffContent

_REMOTE_SCHEMES = ("http://", "https://")
_HEAD_REJECTED_CODES = frozenset({403, 405})
_GONE_CODES = frozenset({404, 410})


class RemoteInputRef(NamedTuple):
    variable_name: str
    url: str


class Reachability(StrEnum):
    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    UNKNOWN = "unknown"


class InputReachability(BaseModel):
    model_config = ConfigDict(frozen=True)

    variable_name: str
    url: str
    reachability: Reachability
    reason: str


class InputReachabilityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdicts: list[InputReachability]

    @property
    def unreachable(self) -> list[InputReachability]:
        return [verdict for verdict in self.verdicts if verdict.reachability is Reachability.UNREACHABLE]

    @property
    def unknown(self) -> list[InputReachability]:
        return [verdict for verdict in self.verdicts if verdict.reachability is Reachability.UNKNOWN]


def _remote_url_of(*, content: StuffContent) -> str | None:
    match content:
        case DocumentContent() | ImageContent():
            return content.url if content.url.startswith(_REMOTE_SCHEMES) else None
        case _:
            return None


def collect_remote_input_refs(*, working_memory: WorkingMemory) -> list[RemoteInputRef]:
    """Every http(s) URL the run's inputs carry, on a Document or Image or inside a list of them."""
    refs: list[RemoteInputRef] = []
    for variable_name, stuff in working_memory.root.items():
        content = stuff.content
        candidates: list[StuffContent]
        if isinstance(content, ListContent):
            candidates = list(cast("ListContent[StuffContent]", content).items)
        else:
            candidates = [content]
        for candidate in candidates:
            url = _remote_url_of(content=candidate)
            if url is not None:
                refs.append(RemoteInputRef(variable_name=variable_name, url=url))
    return refs


def _verdict(*, ref: RemoteInputRef, reachability: Reachability, reason: str) -> InputReachability:
    return InputReachability(variable_name=ref.variable_name, url=ref.url, reachability=reachability, reason=reason)


async def _probe(*, client: httpx.AsyncClient, ref: RemoteInputRef) -> InputReachability:
    headers = {"User-Agent": get_user_agent()}
    try:
        response = await client.head(ref.url, headers=headers)
        status_code = response.status_code
        if status_code in _HEAD_REJECTED_CODES:
            async with client.stream("GET", ref.url, headers={**headers, "Range": "bytes=0-0"}) as get_response:
                status_code = get_response.status_code
    except SsrfBlockedError:
        # Never dialled: whether the fetch may reach a private address is the fetch path's policy.
        return _verdict(ref=ref, reachability=Reachability.UNKNOWN, reason="the host is a private or local address")
    except (httpx.UnsupportedProtocol, httpx.InvalidURL) as exc:
        return _verdict(ref=ref, reachability=Reachability.UNREACHABLE, reason=f"invalid URL ({exc})")
    except httpx.ConnectError:
        return _verdict(ref=ref, reachability=Reachability.UNREACHABLE, reason="the host could not be reached")
    except httpx.TooManyRedirects:
        return _verdict(ref=ref, reachability=Reachability.UNREACHABLE, reason="too many redirects")
    except httpx.TimeoutException:
        return _verdict(ref=ref, reachability=Reachability.UNKNOWN, reason="the host did not answer in time")
    except httpx.HTTPError as exc:
        return _verdict(ref=ref, reachability=Reachability.UNKNOWN, reason=f"the probe failed ({type(exc).__name__})")

    if status_code in _GONE_CODES:
        return _verdict(ref=ref, reachability=Reachability.UNREACHABLE, reason=f"HTTP {status_code}")
    if 200 <= status_code < 400:
        return _verdict(ref=ref, reachability=Reachability.REACHABLE, reason=f"HTTP {status_code}")
    return _verdict(ref=ref, reachability=Reachability.UNKNOWN, reason=f"HTTP {status_code}")


async def probe_remote_inputs(
    *,
    refs: list[RemoteInputRef],
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> InputReachabilityReport:
    """Probe every ref at once. A probe outcome never raises; the report carries the verdicts."""
    if not refs:
        return InputReachabilityReport(verdicts=[])
    async with httpx.AsyncClient(transport=transport or SsrfGuardedTransport(), timeout=timeout_seconds, follow_redirects=True) as client:
        verdicts = await asyncio.gather(*(_probe(client=client, ref=ref) for ref in refs))
    return InputReachabilityReport(verdicts=list(verdicts))


def log_unknown_inputs(*, report: InputReachabilityReport) -> None:
    for verdict in report.unknown:
        log.warning(f"Input '{verdict.variable_name}' at '{verdict.url}' could not be confirmed reachable ({verdict.reason}); the run proceeds")
