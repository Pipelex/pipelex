import socket

import httpcore
import httpx
import pytest
from pytest_mock import MockerFixture

from pipelex.tools.network.exceptions import SsrfBlockedError
from pipelex.tools.network.ssrf_guard import SsrfGuardedTransport, resolve_to_allowed_ip


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
        assert await resolve_to_allowed_ip("example.com", 443) == "93.184.216.34"

    async def test_resolve_blocks_private_resolution(self, mocker: MockerFixture) -> None:
        def fake(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return _addrinfo("169.254.169.254", 80)

        mocker.patch("socket.getaddrinfo", side_effect=fake)
        with pytest.raises(SsrfBlockedError):
            await resolve_to_allowed_ip("attacker.example", 80)

    async def test_resolve_blocks_literal_private_host(self) -> None:
        # A literal private IP never needs resolution — blocked by the cheap rule.
        with pytest.raises(SsrfBlockedError):
            await resolve_to_allowed_ip("10.0.0.5", 80)

    async def test_resolve_blocks_mixed_public_and_private(self, mocker: MockerFixture) -> None:
        # A host resolving to both a public and a private IP is itself a rebinding
        # signal — refuse the whole connection rather than cherry-pick the public one.
        def fake(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return _addrinfo("93.184.216.34", 80) + _addrinfo("127.0.0.1", 80)

        mocker.patch("socket.getaddrinfo", side_effect=fake)
        with pytest.raises(SsrfBlockedError):
            await resolve_to_allowed_ip("rebind.example", 80)

    async def test_resolution_failure_maps_to_connect_error(self, mocker: MockerFixture) -> None:
        # A genuine DNS failure is not a security event — surface httpx's usual connect error.
        mocker.patch("socket.getaddrinfo", side_effect=socket.gaierror("name or service not known"))
        with pytest.raises(httpcore.ConnectError):
            await resolve_to_allowed_ip("nonexistent.invalid", 80)

    async def test_transport_aborts_request_to_private_resolution(self, mocker: MockerFixture) -> None:
        # Drive a real httpx client through the guarded transport: the request must
        # abort before any socket opens, with the typed security error.
        def fake(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return _addrinfo("169.254.169.254", 80)

        mocker.patch("socket.getaddrinfo", side_effect=fake)
        async with httpx.AsyncClient(transport=SsrfGuardedTransport()) as client:
            with pytest.raises(SsrfBlockedError):
                await client.post("http://attacker.example/cb", json={"ping": 1})
