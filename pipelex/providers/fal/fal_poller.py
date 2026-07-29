from __future__ import annotations

from typing import Any, cast

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    retry_if_exception_type,
    retry_if_result,
    stop_after_delay,
    wait_random_exponential,
)

from pipelex.tools.misc.tenacity_utils import log_retry


class FalPoller:
    def _is_transient_http(self, exc: BaseException) -> bool:
        if not isinstance(exc, httpx.HTTPStatusError):
            return False
        code = exc.response.status_code
        return code == 429 or 500 <= code <= 599

    async def poll_queue_until_complete(self, response_dict: dict[str, Any]) -> dict[str, Any]:
        """Poll Queue API until completion and return the final response JSON.

        Expects response_dict to include:
        - status_url (str)
        - response_url (str)

        Reads API key from env var FAL_KEY.
        """
        status_url = response_dict.get("status_url")
        response_url = response_dict.get("response_url")
        if not isinstance(status_url, str) or not isinstance(response_url, str):
            msg = "response_dict must include 'status_url' and 'response_url' as strings"
            raise TypeError(msg)

        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:

            async def _try_once() -> dict[str, Any] | None:
                # 1) poll status
                status = await client.get(status_url)
                status.raise_for_status()  # will be retried on 429/5xx via tenacity

                payload = status.json()
                status = payload.get("status")

                if status in {"IN_QUEUE", "IN_PROGRESS"}:
                    return None  # tells tenacity to retry

                if status == "COMPLETED":
                    # 2) fetch the actual response
                    res = await client.get(response_url)
                    res.raise_for_status()
                    return cast("dict[str, Any]", res.json())

                # Terminal / unexpected states: fail fast (no retry)
                msg = f"fal request ended with status={status!r}: {payload}"
                raise RuntimeError(msg)

            retrying = AsyncRetrying(
                retry=(
                    retry_if_result(lambda r: r is None)
                    | retry_if_exception_type((httpx.TimeoutException, httpx.TransportError))
                    | retry_if_exception(self._is_transient_http)
                ),
                before_sleep=log_retry,
                wait=wait_random_exponential(multiplier=0.5, max=8.0),  # jittered backoff
                stop=stop_after_delay(300.0),  # total polling budget (seconds)
                reraise=True,
            )

            async for attempt in retrying:
                with attempt:
                    result = await _try_once()
                    if result is not None:
                        return result

        msg = "Polling ended unexpectedly"
        raise RuntimeError(msg)
