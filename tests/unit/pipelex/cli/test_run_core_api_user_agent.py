"""The agent CLI's API run path names itself `pipelex-cli` in its `User-Agent`."""

from __future__ import annotations

import asyncio
import platform
import sys
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from mthds.runners.api.client import MthdsAPIClient
from mthds.version import __version__ as mthds_version

from pipelex.cli.agent_cli.commands.run._run_core_api import run_pipeline_core_api  # pyright: ignore[reportPrivateUsage]
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
    @pytest.mark.usefixtures("api_credentials")
    def test_library_client_is_not_labelled_pipelex_cli(self) -> None:
        """A client built as a library user builds it carries no `pipelex-cli` token."""
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
