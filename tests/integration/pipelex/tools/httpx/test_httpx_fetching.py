import pytest

from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx, fetch_file_from_url_httpx_async
from tests.cases import TestURLs


@pytest.mark.codex_disabled
class TestHttpxFetching:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", TestURLs.PUBLIC_URLS)
    async def test_fetch_file_from_url_httpx_async(
        self,
        url: str,
    ) -> None:
        assert (
            await fetch_file_from_url_httpx_async(
                url=url,
                request_timeout=60,
            )
            is not None
        )

    @pytest.mark.parametrize("url", TestURLs.PUBLIC_URLS)
    def test_fetch_file_from_url_httpx(
        self,
        url: str,
    ) -> None:
        assert (
            fetch_file_from_url_httpx(
                url=url,
                request_timeout=60,
            )
            is not None
        )
