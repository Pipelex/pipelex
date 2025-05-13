# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import pytest

from pipelex.tools.misc.file_fetching_helpers import fetch_file_from_url_httpx, fetch_file_from_url_httpx_async
from tests.tools.test_data import TestURLs


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
                timeout=60,
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
                timeout=60,
            )
            is not None
        )
