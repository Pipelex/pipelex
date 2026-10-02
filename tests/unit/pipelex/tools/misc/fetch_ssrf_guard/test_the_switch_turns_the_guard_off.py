"""`is_fetch_ssrf_guard_enabled = false` restores a plain client that follows redirects unvetted."""

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx
from tests.unit.pipelex.tools.misc.fetch_ssrf_guard.loopback import (
    PROXY_ENV_VARS,
    REDIRECT_TO_LOCALHOST_PATH,
    SECRET_BODY,
    SECRET_PATH,
    LoopbackServer,
    loopback_url,
)


@pytest.mark.asyncio(loop_scope="class")
class TestTheSwitchTurnsTheGuardOff:
    async def test_switch_off_fetches_aloopback_url(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        loopback_server: LoopbackServer,
    ) -> None:
        mocker.patch.object(get_config().runtime.network, "is_fetch_ssrf_guard_enabled", False)
        for env_var in PROXY_ENV_VARS:
            monkeypatch.delenv(env_var, raising=False)

        raw_bytes = await fetch_file_from_url_httpx(url=loopback_url(loopback_server, path=SECRET_PATH))

        assert raw_bytes == SECRET_BODY

    async def test_switch_off_follows_redirects_unvetted(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        loopback_server: LoopbackServer,
    ) -> None:
        mocker.patch.object(get_config().runtime.network, "is_fetch_ssrf_guard_enabled", False)
        for env_var in PROXY_ENV_VARS:
            monkeypatch.delenv(env_var, raising=False)

        raw_bytes = await fetch_file_from_url_httpx(url=loopback_url(loopback_server, path=REDIRECT_TO_LOCALHOST_PATH))

        assert raw_bytes == SECRET_BODY
