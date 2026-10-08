import asyncio

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation import doc_gen_generate
from pipelex.cogt.content_generation.doc_gen_generate import RunRenderResources
from pipelex.cogt.doc_gen.exceptions import DocGenRenderError
from pipelex.cogt.doc_gen.render_job import LoadedResource
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageProviderAbstract, StoredData
from pipelex.tools.uri.exceptions import UriReadRefusedError
from pipelex.tools.uri.uri_bytes import UriBytes


@pytest.mark.asyncio(loop_scope="class")
class TestRunRenderResources:
    async def test_a_read_returns_the_bytes_with_the_type_the_source_gives(self, mocker: MockerFixture) -> None:
        """An engine reading from its worker thread gets the file's bytes and the media type its source gave them."""
        storage_uri = f"{PIPELEX_STORAGE_SCHEME}scope/assets/theme"
        storage_provider = mocker.MagicMock(spec=StorageProviderAbstract)
        storage_provider.load_with_metadata = mocker.AsyncMock(return_value=StoredData(data=b"body {}", mime_type="text/css; charset=utf-8"))
        resources = RunRenderResources(storage_provider=storage_provider, read_scope=None, loop=asyncio.get_running_loop())

        loaded = await asyncio.to_thread(resources.load, uri=storage_uri, position="stylesheet 1 of the document")

        assert loaded == LoadedResource(data=b"body {}", mime_type="text/css")

    async def test_a_read_whose_source_gives_no_type_returns_none(self, mocker: MockerFixture) -> None:
        mocker.patch.object(
            doc_gen_generate,
            "load_bytes_and_mime_type_from_any_uri",
            new_callable=mocker.AsyncMock,
            return_value=UriBytes(data=b"\x89PNG", mime_type=None),
        )
        resources = RunRenderResources(
            storage_provider=mocker.MagicMock(spec=StorageProviderAbstract), read_scope=None, loop=asyncio.get_running_loop()
        )

        loaded = await asyncio.to_thread(resources.load, uri="https://example.com/photo", position="image 1 of the document")

        assert loaded == LoadedResource(data=b"\x89PNG", mime_type=None)

    async def test_a_read_outside_the_scope_is_refused_before_loading(self, mocker: MockerFixture) -> None:
        loader = mocker.patch.object(doc_gen_generate, "load_bytes_and_mime_type_from_any_uri", new_callable=mocker.AsyncMock)
        resources = RunRenderResources(
            storage_provider=mocker.MagicMock(spec=StorageProviderAbstract), read_scope="scope-a", loop=asyncio.get_running_loop()
        )

        with pytest.raises(UriReadRefusedError):
            await asyncio.to_thread(resources.load, uri=f"{PIPELEX_STORAGE_SCHEME}scope-b/assets/theme.css", position="stylesheet 1 of the document")

        loader.assert_not_awaited()

    async def test_a_read_that_times_out_is_a_render_error_and_is_cancelled(self, mocker: MockerFixture) -> None:
        """A slow read fails the print with a `DocGenRenderError` naming its position, and stops running on the loop."""
        was_cancelled = asyncio.Event()

        async def _never_answers(uri: str, *, storage_provider: StorageProviderAbstract) -> UriBytes:  # ruff: ignore[unused-function-argument]
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                was_cancelled.set()
                raise
            return UriBytes(data=b"")

        mocker.patch.object(doc_gen_generate, "_RESOURCE_LOAD_TIMEOUT_SECONDS", 0.05)
        mocker.patch.object(doc_gen_generate, "load_bytes_and_mime_type_from_any_uri", _never_answers)
        resources = RunRenderResources(
            storage_provider=mocker.MagicMock(spec=StorageProviderAbstract), read_scope=None, loop=asyncio.get_running_loop()
        )

        with pytest.raises(DocGenRenderError, match="image 1 of the document"):
            await asyncio.to_thread(resources.load, uri="https://example.com/photo.png", position="image 1 of the document")
        await asyncio.wait_for(was_cancelled.wait(), timeout=5)
