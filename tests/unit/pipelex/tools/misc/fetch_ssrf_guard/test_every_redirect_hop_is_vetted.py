"""The guard vets every redirect hop, not only the first request."""

import pytest
from pytest_mock import MockerFixture

from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx
from pipelex.tools.network.exceptions import SsrfBlockedError
from tests.unit.pipelex.tools.misc.fetch_ssrf_guard.loopback import (
    REDIRECT_TO_LOCALHOST_PATH,
    SECRET_BODY,
    SECRET_PATH,
    LoopbackServer,
    loopback_url,
    treat_only_the_localhost_name_as_private,
)


@pytest.mark.asyncio(loop_scope="class")
class TestEveryRedirectHopIsVetted:
    async def test_a_first_hop_the_rules_allow_is_fetched(self, mocker: MockerFixture, loopback_server: LoopbackServer) -> None:
        """The control for the next test: under the patched rules, the loopback server itself is reachable."""
        treat_only_the_localhost_name_as_private(mocker)

        raw_bytes = await fetch_file_from_url_httpx(url=loopback_url(loopback_server, path=SECRET_PATH))

        assert raw_bytes == SECRET_BODY

    async def test_a_redirect_to_a_private_destination_is_refused(self, mocker: MockerFixture, loopback_server: LoopbackServer) -> None:
        treat_only_the_localhost_name_as_private(mocker)

        with pytest.raises(SsrfBlockedError, match="localhost"):
            await fetch_file_from_url_httpx(url=loopback_url(loopback_server, path=REDIRECT_TO_LOCALHOST_PATH))

        assert loopback_server.hits == [REDIRECT_TO_LOCALHOST_PATH]
