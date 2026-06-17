"""DNS-rebinding-safe httpx transport for caller-supplied outbound URLs.

A request-time literal-IP check (``is_disallowed_host``) cannot stop SSRF via DNS
rebinding: ``https://attacker.example/cb`` passes validation, but its A record can
resolve to ``169.254.169.254`` / a private range by the time the worker fires the
request. :class:`SsrfGuardedTransport` closes that gap by re-resolving the host at
connect time, checking every candidate IP against the shared rule, and connecting
to a *vetted* IP (so a rebind between the check and the socket open is impossible).

On the pinned ``httpx`` 0.28.1 / ``httpcore`` 1.0.9, the connect happens in the
network backend's ``connect_tcp(host, port, ...)``, while TLS SNI / cert
verification and the ``Host`` header keep using the origin hostname (httpcore
derives ``server_hostname`` from the origin, not from what ``connect_tcp``
dials — see ``httpcore._async.connection.AsyncHTTPConnection._connect``). Wrapping
the backend therefore vets the destination IP without disturbing TLS or routing.
"""

from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING

import httpcore
import httpx
from typing_extensions import override

from pipelex.tools.network.exceptions import SsrfBlockedError
from pipelex.tools.network.host_rules import is_disallowed_host, is_disallowed_ip

if TYPE_CHECKING:
    from collections.abc import Iterable

    from httpcore import SOCKET_OPTION


async def resolve_to_allowed_ips(
    host: str,
    *,
    port: int,
    timeout: float | None = None,  # noqa: ASYNC109 — propagates httpcore's connect timeout to bound DNS resolution
) -> list[str]:
    """Resolve ``host`` and return every IP that passes the disallowed-host rule.

    Raises :class:`SsrfBlockedError` when ``host`` is a literal disallowed host or
    resolves to *any* disallowed (private/loopback/metadata) address — a mixed
    public/private resolution is itself a rebinding signal, so the whole
    connection is refused rather than cherry-picking the allowed records. Every IP
    in the returned list is vetted, so the caller may dial any of them (and fall
    back across them) with no rebind window.

    A plain DNS-resolution failure is mapped to :class:`httpcore.ConnectError`,
    and a resolution that exceeds ``timeout`` to :class:`httpcore.ConnectTimeout`,
    so httpx surfaces them as the usual connect errors rather than security
    errors. Bounding resolution by ``timeout`` keeps the httpx connect timeout
    covering DNS too — stock httpcore resolves inside the same deadline, but here
    resolution happens in a separate step.
    """
    if is_disallowed_host(host):
        msg = f"Refusing to connect to {host!r}: destination is a disallowed (private/loopback/metadata) address."
        raise SsrfBlockedError(msg)
    loop = asyncio.get_running_loop()
    getaddrinfo_coro = loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    try:
        if timeout is None:
            addr_infos = await getaddrinfo_coro
        else:
            addr_infos = await asyncio.wait_for(getaddrinfo_coro, timeout=timeout)
    except socket.gaierror as exc:
        msg = f"Could not resolve host {host!r}."
        raise httpcore.ConnectError(msg) from exc
    except asyncio.TimeoutError as exc:  # noqa: UP041 — asyncio.TimeoutError is distinct from builtin TimeoutError pre-3.11; project targets 3.10+
        msg = f"Timed out resolving host {host!r}."
        raise httpcore.ConnectTimeout(msg) from exc
    resolved_ips = [str(addr_info[4][0]) for addr_info in addr_infos]
    # Fail closed: if resolution yielded no address to vet, refuse rather than
    # fall through. getaddrinfo raises on failure today, but the guard's contract
    # is "return vetted IPs or raise" — never return an unvetted destination.
    if not resolved_ips:
        msg = f"Refusing to connect to {host!r}: name resolved to no addresses."
        raise SsrfBlockedError(msg)
    if any(is_disallowed_ip(resolved_ip) for resolved_ip in resolved_ips):
        msg = f"Refusing to connect to {host!r}: it resolved to a disallowed (private/loopback/metadata) address."
        raise SsrfBlockedError(msg)
    return resolved_ips


class SsrfGuardedBackend(httpcore.AsyncNetworkBackend):
    """Wraps another network backend, vetting the destination IP before connecting.

    Only ``connect_tcp`` carries the guard — it is the sole DNS-resolving entry
    point for the http(s) origins webhooks use. ``connect_unix_socket`` / ``sleep``
    delegate unchanged.
    """

    def __init__(self, inner: httpcore.AsyncNetworkBackend) -> None:
        self._inner = inner

    @override
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 — mandated by the AsyncNetworkBackend interface being overridden
        local_address: str | None = None,
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        # ``timeout`` bounds the WHOLE connect (DNS + every fallback dial), matching
        # stock httpcore semantics — not each attempt separately, which would let a
        # multi-IP host balloon to (N+1)x the configured timeout. Track a single
        # monotonic deadline and hand each step only the time left in the budget.
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + timeout
        vetted_ips = await resolve_to_allowed_ips(host, port=port, timeout=timeout)
        # Every IP is pre-vetted, so dialing any literal is rebind-safe (getaddrinfo
        # on an IP literal does no DNS). Try them in order and fall back on connect
        # failure, restoring the multi-address resilience (dual-stack / multiple A
        # records) that pinning to a single IP would lose.
        last_exc: httpcore.ConnectError | httpcore.ConnectTimeout | None = None
        for vetted_ip in vetted_ips:
            remaining = None if deadline is None else max(0.0, deadline - loop.time())
            try:
                return await self._inner.connect_tcp(
                    host=vetted_ip,
                    port=port,
                    timeout=remaining,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_exc = exc
        # vetted_ips is never empty (resolve_to_allowed_ips raises otherwise), so the
        # loop ran at least once and a connect error was recorded for every candidate.
        assert last_exc is not None
        raise last_exc

    @override
    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 — mandated by the AsyncNetworkBackend interface being overridden
        socket_options: Iterable[SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._inner.connect_unix_socket(path, timeout=timeout, socket_options=socket_options)

    @override
    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class SsrfGuardedTransport(httpx.AsyncHTTPTransport):
    """An :class:`httpx.AsyncHTTPTransport` that vets every destination IP at connect.

    Use for any outbound request to a caller-supplied URL (webhook delivery). The
    transport re-resolves the host at connect time and refuses private/metadata
    destinations, raising :class:`SsrfBlockedError`.
    """

    def __init__(self) -> None:
        super().__init__()
        # httpx 0.28.1 exposes no public seam to inject a network backend, so wrap
        # the connection pool's backend in place (before any connection is built).
        self._pool._network_backend = SsrfGuardedBackend(self._pool._network_backend)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
