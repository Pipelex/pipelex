import asyncio

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation import doc_gen_generate
from pipelex.cogt.content_generation.doc_gen_generate import RunRenderResources
from pipelex.cogt.doc_gen.exceptions import DocGenRenderError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


@pytest.mark.asyncio(loop_scope="class")
class TestRunRenderResources:
    async def test_a_read_that_times_out_is_a_render_error_and_is_cancelled(self, mocker: MockerFixture) -> None:
        """A slow read fails the print with a `DocGenRenderError` naming its position, and stops running on the loop."""
        was_cancelled = asyncio.Event()

        async def _never_answers(uri: str, *, storage_provider: StorageProviderAbstract) -> bytes:  # ruff: ignore[unused-function-argument]
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                was_cancelled.set()
                raise
            return b""

        mocker.patch.object(doc_gen_generate, "_RESOURCE_LOAD_TIMEOUT_SECONDS", 0.05)
        mocker.patch.object(doc_gen_generate, "load_bytes_from_any_uri", _never_answers)
        resources = RunRenderResources(storage_provider=mocker.MagicMock(spec=StorageProviderAbstract), read_scope=None, loop=asyncio.get_running_loop())

        with pytest.raises(DocGenRenderError, match="image 1 of the document"):
            await asyncio.to_thread(resources.load, uri="https://example.com/photo.png", position="image 1 of the document")
        await asyncio.wait_for(was_cancelled.wait(), timeout=5)
