"""A crate route resolves off the event loop, so a stalled resolution never holds up the server's other requests.

`project_resolved_method` writes, loads, projects and tears the method down in one worker thread. Were any of it to
run on the event loop again, the stalled resolution below would freeze every other request on the worker until it
gave up, and the request sent meanwhile could not complete. The stall happens before the first load, so the two
requests never load a library at the same time.
"""

import asyncio
import threading
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipeline.resolve_bundle import resolve_crate_from_method_dir
from pytest_mock import MockerFixture

from pipelex_api.exception_handlers import register_exception_handlers
from pipelex_api.routes import router as api_router
from tests.unit._constants import VALID_MTHDS

#: How long the stalled resolution waits to be released before it gives up, which bounds a regression's run.
_STALL_TIMEOUT_SECONDS = 10.0
_REQUEST_TIMEOUT_SECONDS = 30.0


class TestCrateRouteConcurrency:
    @pytest.mark.asyncio
    async def test_an_unrelated_request_completes_while_a_resolution_is_stalled(self, mocker: MockerFixture):
        entered = threading.Event()
        release = threading.Event()

        def _resolve_after_a_stall(*, method_dir: Path, methods_dirs: list[Path] | None = None) -> LibraryCrate:
            # Only the first resolution stalls; every later one, the unrelated request's included, resolves at once.
            if not entered.is_set():
                entered.set()
                if not release.wait(timeout=_STALL_TIMEOUT_SECONDS):
                    msg = "the stalled resolution was never released"
                    raise AssertionError(msg)
            return resolve_crate_from_method_dir(method_dir=method_dir, methods_dirs=methods_dirs)

        mocker.patch("pipelex_api.routes.pipelex.crate_ops.resolve_crate_from_method_dir", side_effect=_resolve_after_a_stall)
        app = FastAPI()
        app.include_router(api_router, prefix="/v1")
        register_exception_handlers(app)
        body = {"files": {"main.mthds": VALID_MTHDS}}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://runner") as client:
            stalled = asyncio.create_task(client.post("/v1/resolve", json=body))
            assert await asyncio.to_thread(entered.wait, _STALL_TIMEOUT_SECONDS), "the first resolution never started"
            try:
                unrelated = await asyncio.wait_for(client.post("/v1/resolve", json=body), timeout=_REQUEST_TIMEOUT_SECONDS)
                assert not stalled.done(), "the stalled resolution answered before it was released"
            finally:
                release.set()
            first = await asyncio.wait_for(stalled, timeout=_REQUEST_TIMEOUT_SECONDS)

        assert unrelated.status_code == 200, unrelated.text
        assert unrelated.json()["is_valid"] is True, unrelated.text
        assert first.status_code == 200, first.text
        assert first.json()["is_valid"] is True, first.text
