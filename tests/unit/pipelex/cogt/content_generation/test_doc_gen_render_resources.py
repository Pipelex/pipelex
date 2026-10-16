import asyncio
from urllib.parse import urljoin

import pytest
from mthds.method_tree.vocabulary import TreeRefusalCode
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation import doc_gen_generate
from pipelex.cogt.content_generation.doc_gen_generate import RunRenderResources
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.document_composition import DocumentComposition
from pipelex.cogt.doc_gen.exceptions import DocGenRenderError, TemplateUrlRefusedError
from pipelex.cogt.doc_gen.layout_tree import LayoutDocument
from pipelex.cogt.doc_gen.method_file_urls import RelativeUrlBase
from pipelex.cogt.doc_gen.render_job import METHOD_FILE_URL_PREFIX, LoadedResource
from pipelex.core.method_trees.method_file_store import HeldFile, LocalMethodFileStore
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageProviderAbstract, StoredData
from pipelex.tools.uri.exceptions import UriReadRefusedError
from pipelex.tools.uri.uri_bytes import UriBytes

_METHOD_FILES = {
    "main.mthds": b'domain = "letters"\n',
    "templates/letter.html": b'<img src="logo.png">',
    "templates/logo.png": b"\x89PNG logo",
    "styles/print.css": b"@font-face { src: url(../fonts/brand.woff2) }",
    "fonts/brand.woff2": b"wOF2 brand",
}


def _html_document(*, url_base: RelativeUrlBase | None) -> DocumentComposition:
    return DocumentComposition(
        format=DocGenFormat.PDF, source=DocGenSource.HTML, filename="letter.pdf", title="Letter", html="<p>Letter</p>", url_base=url_base
    )


def _template_url_base(*, tree_digest: str) -> RelativeUrlBase:
    return RelativeUrlBase(tree_digest=tree_digest, holder="templates/letter.html", template_label="the template file 'templates/letter.html'")


@pytest.mark.asyncio(loop_scope="class")
class TestRunRenderResources:
    @pytest.fixture
    def method_store(self, mocker: MockerFixture) -> LocalMethodFileStore:
        """A method file store of the test's own, as the one the print reads method files through."""
        store = LocalMethodFileStore()
        mocker.patch("pipelex.core.method_trees.method_files.get_method_file_store", return_value=store)
        return store

    async def test_a_url_joined_to_the_base_reads_the_method_file_through_the_store(
        self, mocker: MockerFixture, method_store: LocalMethodFileStore
    ) -> None:
        """The image beside the template, a stylesheet and the font it names are read from the tree, the listing once."""
        tree = method_store.hold_files(holder="library", files={path: HeldFile.of_bytes(data=data) for path, data in _METHOD_FILES.items()})
        url_base = _template_url_base(tree_digest=tree.digest)
        listing_spy = mocker.spy(method_store, "read_tree_listing")
        loader = mocker.patch.object(doc_gen_generate, "load_bytes_and_mime_type_from_any_uri", new_callable=mocker.AsyncMock)
        resources = RunRenderResources(
            storage_provider=mocker.MagicMock(spec=StorageProviderAbstract),
            read_scope="org/acme",
            loop=asyncio.get_running_loop(),
            document=_html_document(url_base=url_base),
        )
        logo_url = urljoin(url_base.base_url, "logo.png")
        stylesheet_url = urljoin(url_base.base_url, "../styles/print.css")
        font_url = urljoin(stylesheet_url, "../fonts/brand.woff2")

        loaded = [await asyncio.to_thread(resources.load, uri=url, position="a file of the document") for url in (logo_url, stylesheet_url, font_url)]

        assert loaded == [
            LoadedResource(data=_METHOD_FILES["templates/logo.png"], mime_type=None),
            LoadedResource(data=_METHOD_FILES["styles/print.css"], mime_type=None),
            LoadedResource(data=_METHOD_FILES["fonts/brand.woff2"], mime_type=None),
        ]
        listing_spy.assert_called_once_with(tree_digest=tree.digest, read_scope="org/acme")
        loader.assert_not_awaited()

    async def test_a_relative_url_handed_as_written_resolves_against_the_template(
        self, mocker: MockerFixture, method_store: LocalMethodFileStore
    ) -> None:
        tree = method_store.hold_files(holder="library", files={path: HeldFile.of_bytes(data=data) for path, data in _METHOD_FILES.items()})
        resources = RunRenderResources(
            storage_provider=mocker.MagicMock(spec=StorageProviderAbstract),
            read_scope=None,
            loop=asyncio.get_running_loop(),
            document=_html_document(url_base=_template_url_base(tree_digest=tree.digest)),
        )

        loaded = await asyncio.to_thread(resources.load, uri="../fonts/brand.woff2", position="font 1 of the document")

        assert loaded == LoadedResource(data=_METHOD_FILES["fonts/brand.woff2"], mime_type=None)

    @pytest.mark.parametrize(
        ("written", "code", "named"),
        [
            pytest.param("../../secret.txt", TreeRefusalCode.REFERENCE_LEAVES_TREE, "climbs above the root", id="climbs_above_the_root"),
            pytest.param("/etc/passwd", TreeRefusalCode.REFERENCE_LEAVES_TREE, "starts with '/'", id="root_relative"),
            pytest.param("missing.png", TreeRefusalCode.REFERENCE_NOT_IN_TREE, "'templates/missing.png', which is not a file", id="absent"),
        ],
    )
    async def test_a_url_naming_no_file_of_the_tree_is_refused_and_nothing_else_is_read(
        self, mocker: MockerFixture, method_store: LocalMethodFileStore, written: str, code: TreeRefusalCode, named: str
    ) -> None:
        tree = method_store.hold_files(holder="library", files={path: HeldFile.of_bytes(data=data) for path, data in _METHOD_FILES.items()})
        url_base = _template_url_base(tree_digest=tree.digest)
        loader = mocker.patch.object(doc_gen_generate, "load_bytes_and_mime_type_from_any_uri", new_callable=mocker.AsyncMock)
        blob_spy = mocker.spy(method_store, "read_blob")
        resources = RunRenderResources(
            storage_provider=mocker.MagicMock(spec=StorageProviderAbstract),
            read_scope=None,
            loop=asyncio.get_running_loop(),
            document=_html_document(url_base=url_base),
        )

        with pytest.raises(TemplateUrlRefusedError) as exc_info:
            await asyncio.to_thread(resources.load, uri=urljoin(url_base.base_url, written), position="image 1 of the document")

        assert exc_info.value.refusal_code == code
        assert exc_info.value.message.startswith("Refused to read image 1 of the document.")
        assert named in exc_info.value.message
        assert "the template file 'templates/letter.html'" in exc_info.value.message
        loader.assert_not_awaited()
        blob_spy.assert_not_called()

    async def test_a_relative_url_of_html_with_no_method_tree_is_refused_and_never_read_from_disk(self, mocker: MockerFixture) -> None:
        """A template that belongs to no method tree names no file by a relative URL, so no local path is ever opened."""
        loader = mocker.patch.object(doc_gen_generate, "load_bytes_and_mime_type_from_any_uri", new_callable=mocker.AsyncMock)
        resources = RunRenderResources(
            storage_provider=mocker.MagicMock(spec=StorageProviderAbstract),
            read_scope=None,
            loop=asyncio.get_running_loop(),
            document=_html_document(url_base=None),
        )

        for uri in ("logo.png", "../../etc/passwd", f"{METHOD_FILE_URL_PREFIX}{'ab' * 32}/logo.png"):
            with pytest.raises(TemplateUrlRefusedError) as exc_info:
                await asyncio.to_thread(resources.load, uri=uri, position="image 1 of the document")
            assert exc_info.value.refusal_code is None
            assert "belongs to no method's folder" in exc_info.value.message
        loader.assert_not_awaited()

    async def test_a_url_with_a_scheme_in_an_html_print_is_read_as_it_names(self, mocker: MockerFixture, method_store: LocalMethodFileStore) -> None:
        tree = method_store.hold_files(holder="library", files={path: HeldFile.of_bytes(data=data) for path, data in _METHOD_FILES.items()})
        loader = mocker.patch.object(
            doc_gen_generate,
            "load_bytes_and_mime_type_from_any_uri",
            new_callable=mocker.AsyncMock,
            return_value=UriBytes(data=b"\x89PNG remote", mime_type="image/png"),
        )
        listing_spy = mocker.spy(method_store, "read_tree_listing")
        resources = RunRenderResources(
            storage_provider=mocker.MagicMock(spec=StorageProviderAbstract),
            read_scope=None,
            loop=asyncio.get_running_loop(),
            document=_html_document(url_base=_template_url_base(tree_digest=tree.digest)),
        )

        loaded = await asyncio.to_thread(resources.load, uri="https://cdn.example.com/logo.png", position="image 1 of the document")

        assert loaded == LoadedResource(data=b"\x89PNG remote", mime_type="image/png")
        loader.assert_awaited_once()
        listing_spy.assert_not_called()

    async def test_a_print_with_no_html_reads_a_local_path_as_it_did(self, mocker: MockerFixture) -> None:
        """A layout's image is a URI the step's data gave, never a file of a method tree, so a local path keeps its arm."""
        loader = mocker.patch.object(
            doc_gen_generate,
            "load_bytes_and_mime_type_from_any_uri",
            new_callable=mocker.AsyncMock,
            return_value=UriBytes(data=b"\x89PNG local", mime_type=None),
        )
        layout_document = DocumentComposition(
            format=DocGenFormat.PDF,
            source=DocGenSource.LAYOUT,
            filename="letter.pdf",
            title="Letter",
            layout=LayoutDocument(title="Letter", blocks=[]),
        )
        resources = RunRenderResources(
            storage_provider=mocker.MagicMock(spec=StorageProviderAbstract),
            read_scope=None,
            loop=asyncio.get_running_loop(),
            document=layout_document,
        )

        loaded = await asyncio.to_thread(resources.load, uri="images/photo.png", position="image 1 of the document")

        assert loaded == LoadedResource(data=b"\x89PNG local", mime_type=None)
        loader.assert_awaited_once()

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
