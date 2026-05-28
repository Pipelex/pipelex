import socket
import time
from typing import cast

import httpcore
import httpx
import pytest
from pytest_mock import MockerFixture

from pipelex.tools.network.exceptions import SsrfBlockedError
from pipelex.tools.network.ssrf_guard import SsrfGuardedBackend, SsrfGuardedTransport, resolve_to_allowed_ips


def _addrinfo(host_ip: str, port: int) -> list[tuple[int, int, int, str, tuple[str, int]]]:
    """Build a getaddrinfo-shaped result for a single resolved IP."""
    family = int(socket.AF_INET6 if ":" in host_ip else socket.AF_INET)
    return [(family, int(socket.SOCK_STREAM), 6, "", (host_ip, port))]


@pytest.mark.asyncio(loop_scope="class")
class TestSsrfGuard:
    async def test_resolve_returns_public_ip(self, mocker: MockerFixture) -> None:
        def fake(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return _addrinfo("93.184.216.34", 443)

        mocker.patch("socket.getaddrinfo", side_effect=fake)
        assert await resolve_to_allowed_ips("example.com", 443) == ["93.184.216.34"]

    async def test_resolve_returns_all_public_ips_in_order(self, mocker: MockerFixture) -> None:
        # Every vetted IP is returned (not just the first) so the caller can fall back.
        def fake(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return _addrinfo("93.184.216.34", 443) + _addrinfo("8.8.8.8", 443)

        mocker.patch("socket.getaddrinfo", side_effect=fake)
        assert await resolve_to_allowed_ips("example.com", 443) == ["93.184.216.34", "8.8.8.8"]

    async def test_resolve_blocks_private_resolution(self, mocker: MockerFixture) -> None:
        def fake(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return _addrinfo("169.254.169.254", 80)

        mocker.patch("socket.getaddrinfo", side_effect=fake)
        with pytest.raises(SsrfBlockedError):
            await resolve_to_allowed_ips("attacker.example", 80)

    async def test_resolve_blocks_literal_private_host(self) -> None:
        # A literal private IP never needs resolution — blocked by the cheap rule.
        with pytest.raises(SsrfBlockedError):
            await resolve_to_allowed_ips("10.0.0.5", 80)

    async def test_resolve_blocks_mixed_public_and_private(self, mocker: MockerFixture) -> None:
        # A host resolving to both a public and a private IP is itself a rebinding
        # signal — refuse the whole connection rather than cherry-pick the public one.
        def fake(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return _addrinfo("93.184.216.34", 80) + _addrinfo("127.0.0.1", 80)

        mocker.patch("socket.getaddrinfo", side_effect=fake)
        with pytest.raises(SsrfBlockedError):
            await resolve_to_allowed_ips("rebind.example", 80)

    async def test_resolution_failure_maps_to_connect_error(self, mocker: MockerFixture) -> None:
        # A genuine DNS failure is not a security event — surface httpx's usual connect error.
        mocker.patch("socket.getaddrinfo", side_effect=socket.gaierror("name or service not known"))
        with pytest.raises(httpcore.ConnectError):
            await resolve_to_allowed_ips("nonexistent.invalid", 80)

    async def test_resolution_timeout_maps_to_connect_timeout(self, mocker: MockerFixture) -> None:
        # DNS resolution is bounded by the connect timeout; a slow resolver surfaces as
        # httpcore.ConnectTimeout (→ httpx.ConnectTimeout), not an unbounded hang.
        def slow(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            time.sleep(0.2)
            return _addrinfo("93.184.216.34", 80)

        mocker.patch("socket.getaddrinfo", side_effect=slow)
        with pytest.raises(httpcore.ConnectTimeout):
            await resolve_to_allowed_ips("slow.example", 80, timeout=0.01)

    async def test_connect_falls_back_across_vetted_ips(self, mocker: MockerFixture) -> None:
        # First vetted IP is unreachable; the guard must fall back to the next vetted IP.
        def fake(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return _addrinfo("93.184.216.34", 80) + _addrinfo("8.8.8.8", 80)

        mocker.patch("socket.getaddrinfo", side_effect=fake)
        mock_inner = mocker.AsyncMock(spec=httpcore.AsyncNetworkBackend)
        sentinel = mocker.Mock(spec=httpcore.AsyncNetworkStream)
        mock_inner.connect_tcp.side_effect = [httpcore.ConnectError("first down"), sentinel]
        backend = SsrfGuardedBackend(cast("httpcore.AsyncNetworkBackend", mock_inner))

        result = await backend.connect_tcp("multi.example", 80, timeout=1.0)

        assert result is sentinel
        assert mock_inner.connect_tcp.await_count == 2
        assert mock_inner.connect_tcp.call_args_list[0].kwargs["host"] == "93.184.216.34"
        assert mock_inner.connect_tcp.call_args_list[1].kwargs["host"] == "8.8.8.8"

    async def test_connect_raises_when_all_vetted_ips_fail(self, mocker: MockerFixture) -> None:
        # When every vetted candidate fails, the last connect error propagates.
        def fake(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return _addrinfo("93.184.216.34", 80) + _addrinfo("8.8.8.8", 80)

        mocker.patch("socket.getaddrinfo", side_effect=fake)
        mock_inner = mocker.AsyncMock(spec=httpcore.AsyncNetworkBackend)
        mock_inner.connect_tcp.side_effect = [httpcore.ConnectError("a down"), httpcore.ConnectError("b down")]
        backend = SsrfGuardedBackend(cast("httpcore.AsyncNetworkBackend", mock_inner))

        with pytest.raises(httpcore.ConnectError):
            await backend.connect_tcp("multi.example", 80, timeout=1.0)
        assert mock_inner.connect_tcp.await_count == 2

    async def test_connect_shares_timeout_budget_across_fallback(self, mocker: MockerFixture) -> None:
        # The single connect timeout bounds DNS + every fallback dial together, so a later
        # attempt sees the REMAINING budget, not a fresh full timeout (which would let a
        # multi-IP host balloon to (N+1)x the configured timeout).
        def fake(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return _addrinfo("93.184.216.34", 80) + _addrinfo("8.8.8.8", 80)

        mocker.patch("socket.getaddrinfo", side_effect=fake)
        timeouts_seen: list[float | None] = []
        sentinel = mocker.Mock(spec=httpcore.AsyncNetworkStream)

        def record(*, timeout: float | None, **_kwargs: object) -> object:
            timeouts_seen.append(timeout)
            if len(timeouts_seen) == 1:
                time.sleep(0.05)  # consume real time so the shared deadline shrinks measurably
                err_msg = "first down"
                raise httpcore.ConnectError(err_msg)
            return sentinel

        mock_inner = mocker.AsyncMock(spec=httpcore.AsyncNetworkBackend)
        mock_inner.connect_tcp.side_effect = record
        backend = SsrfGuardedBackend(cast("httpcore.AsyncNetworkBackend", mock_inner))

        result = await backend.connect_tcp("multi.example", 80, timeout=1.0)

        assert result is sentinel
        assert len(timeouts_seen) == 2
        assert timeouts_seen[0] is not None
        assert timeouts_seen[1] is not None
        assert timeouts_seen[1] < timeouts_seen[0] <= 1.0

    async def test_transport_aborts_request_to_private_resolution(self, mocker: MockerFixture) -> None:
        # Drive a real httpx client through the guarded transport: the request must
        # abort before any socket opens, with the typed security error.
        def fake(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return _addrinfo("169.254.169.254", 80)

        mocker.patch("socket.getaddrinfo", side_effect=fake)
        async with httpx.AsyncClient(transport=SsrfGuardedTransport()) as client:
            with pytest.raises(SsrfBlockedError):
                await client.post("http://attacker.example/cb", json={"ping": 1})
