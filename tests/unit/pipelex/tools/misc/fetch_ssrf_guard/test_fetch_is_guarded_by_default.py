"""The fetch helper refuses a private destination when nobody passes anything."""

import pytest
from pytest_mock import MockerFixture

from pipelex.runtime_hub import RuntimeHub
from pipelex.tools.misc.file_fetch_utils import fetch_file_and_content_type_from_url_httpx, fetch_file_from_url_httpx
from pipelex.tools.network.exceptions import SsrfBlockedError
from tests.unit.pipelex.tools.misc.fetch_ssrf_guard.loopback import SECRET_PATH, LoopbackServer, loopback_url


@pytest.mark.asyncio(loop_scope="class")
class TestFetchIsGuardedByDefault:
    async def test_a_loopback_url_is_refused_before_any_request(self, loopback_server: LoopbackServer) -> None:
        with pytest.raises(SsrfBlockedError) as exc_info:
            await fetch_file_from_url_httpx(url=loopback_url(loopback_server, path=SECRET_PATH))

        assert exc_info.type is SsrfBlockedError
        assert loopback_server.hits == []

    async def test_the_content_type_variant_is_guarded_too(self, loopback_server: LoopbackServer) -> None:
        with pytest.raises(SsrfBlockedError):
            await fetch_file_and_content_type_from_url_httpx(loopback_url(loopback_server, path=SECRET_PATH))

        assert loopback_server.hits == []

    async def test_a_process_with_no_config_loaded_is_guarded(self, mocker: MockerFixture, loopback_server: LoopbackServer) -> None:
        mocker.patch.object(RuntimeHub, "_instance", None)

        with pytest.raises(SsrfBlockedError):
            await fetch_file_from_url_httpx(url=loopback_url(loopback_server, path=SECRET_PATH))

        assert loopback_server.hits == []
