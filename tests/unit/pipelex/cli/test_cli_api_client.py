"""The CLIs' API runner names itself `pipelex-cli` in its `User-Agent`, and only on the CLI path."""

from __future__ import annotations

import asyncio
import platform
import re
import sys
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from mthds.runners.api.client import MthdsAPIClient
from mthds.version import __version__ as mthds_version

from pipelex.cli.agent_cli.commands.run._run_core_api import run_pipeline_core_api  # pyright: ignore[reportPrivateUsage]
from pipelex.cli.cli_api_client import PIPELEX_CLI_APP_NAME, make_pipelex_cli_api_client, pipelex_cli_app_info
from pipelex.tools.misc.package_utils import get_package_version

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _expected_user_agent() -> str:
    version_info = sys.version_info
    runtime = f"python/{version_info.major}.{version_info.minor}.{version_info.micro}"
    platform_parts = [part for part in (platform.system().lower(), platform.machine()) if part]
    if platform_parts:
        runtime += f" ({'; '.join(platform_parts)})"
    return f"pipelex-cli/{get_package_version()} mthds-python/{mthds_version} {runtime}"


@pytest.fixture
def api_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MTHDS_API_KEY", "test-key")
    monkeypatch.setenv("MTHDS_BASE_URL", "https://runner.example.test")


class TestPipelexCliApiClient:
    def test_app_info_names_the_cli_with_the_package_version(self) -> None:
        app_info = pipelex_cli_app_info()
        assert app_info.name == PIPELEX_CLI_APP_NAME == "pipelex-cli"
        assert app_info.version == get_package_version()
        assert app_info.url is None
        assert app_info.details == ()

    @pytest.mark.usefixtures("api_credentials")
    def test_cli_client_user_agent_leads_with_pipelex_cli(self) -> None:
        client = make_pipelex_cli_api_client()
        assert client.user_agent == _expected_user_agent()
        assert re.fullmatch(r"pipelex-cli/\S+ mthds-python/\S+ python/\d+\.\d+\.\d+( \(.+\))?", client.user_agent)

    @pytest.mark.usefixtures("api_credentials")
    def test_library_client_is_not_labelled_pipelex_cli(self) -> None:
        """A client built without the CLI factory, as a library user builds it, carries no `pipelex-cli` token."""
        client = MthdsAPIClient()
        assert "pipelex-cli" not in client.user_agent
        assert client.user_agent.startswith(f"mthds-python/{mthds_version} ")

    @pytest.mark.usefixtures("api_credentials")
    def test_api_run_sends_pipelex_cli_user_agent(self, mocker: MockerFixture) -> None:
        """The agent CLI's API run path sends the `pipelex-cli` header on the wire."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(500, json={"detail": "stop here"})

        real_async_client = httpx.AsyncClient

        def async_client_with_mock_transport(**kwargs: Any) -> httpx.AsyncClient:
            return real_async_client(transport=httpx.MockTransport(handler), **kwargs)

        mocker.patch("mthds.runners.api.client.httpx.AsyncClient", side_effect=async_client_with_mock_transport)

        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(run_pipeline_core_api("some_pipe"))

        assert len(captured) == 1
        assert captured[0].url == "https://runner.example.test/v1/execute"
        assert captured[0].headers["User-Agent"] == _expected_user_agent()
