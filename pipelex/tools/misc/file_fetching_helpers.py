# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

import httpx
from httpx import Response


async def fetch_file_from_url_httpx_async(
    url: str,
    timeout: Optional[int] = None,
) -> bytes:
    async with httpx.AsyncClient() as client:
        response: Response = await client.get(
            url,
            timeout=timeout,
            follow_redirects=True,
        )
        response.raise_for_status()  # Raise exception for 4XX/5XX status codes

        bytes_content: bytes = response.content
        return bytes_content


def fetch_file_from_url_httpx(
    url: str,
    timeout: Optional[int] = None,
) -> bytes:
    with httpx.Client() as client:
        response: Response = client.get(
            url,
            timeout=timeout,
            follow_redirects=True,
        )
        response.raise_for_status()  # Raise exception for 4XX/5XX status codes

        bytes_content: bytes = response.content
        return bytes_content
