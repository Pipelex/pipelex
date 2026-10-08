import base64
from pathlib import Path

import httpx
import pytest
from pytest_mock import MockerFixture

from pipelex.tools.misc.file_fetch_utils import fetch_file_and_content_type_from_url_httpx
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageProviderAbstract, StoredData
from pipelex.tools.uri import uri_bytes
from pipelex.tools.uri.uri_bytes import UriBytes, load_bytes_and_mime_type_from_any_uri, load_bytes_from_any_uri

CSS_BYTES = b"body { color: navy; }"
STYLESHEET_URL = "https://fonts.example.com/css2?family=Inter"


def _data_url(*, declared_type: str, body: bytes) -> str:
    return f"data:{declared_type};base64,{base64.b64encode(body).decode('ascii')}"


def _serve_from(*, mocker: MockerFixture, response: httpx.Response) -> None:
    """Route the loader's fetch through a transport answering `response`, so the real header handling runs."""
    transport = httpx.MockTransport(lambda _request: response)

    async def _fetch_through_transport(url: str, **_kwargs: object) -> tuple[bytes, str | None]:
        return await fetch_file_and_content_type_from_url_httpx(url, transport=transport)

    mocker.patch.object(uri_bytes, "fetch_file_and_content_type_from_url_httpx", _fetch_through_transport)


@pytest.mark.asyncio(loop_scope="class")
class TestLoadBytesAndMimeTypeFromAnyUri:
    """The loader returns a file's bytes with the media type its source gives it, and never guesses one."""

    async def test_an_https_url_returns_the_type_the_response_declares(self, mocker: MockerFixture) -> None:
        """A URL with no extension still says what it serves: the response's `Content-Type`, bare and lowercased."""
        _serve_from(mocker=mocker, response=httpx.Response(200, content=CSS_BYTES, headers={"Content-Type": "Text/CSS; charset=utf-8"}))

        loaded = await load_bytes_and_mime_type_from_any_uri(STYLESHEET_URL)

        assert loaded == UriBytes(data=CSS_BYTES, mime_type="text/css")

    async def test_an_https_url_whose_response_declares_no_type_returns_none(self, mocker: MockerFixture) -> None:
        _serve_from(mocker=mocker, response=httpx.Response(200, content=CSS_BYTES))

        loaded = await load_bytes_and_mime_type_from_any_uri(STYLESHEET_URL)

        assert loaded == UriBytes(data=CSS_BYTES, mime_type=None)

    async def test_a_declared_octet_stream_is_returned_as_declared(self, mocker: MockerFixture) -> None:
        """A generic type says nothing, but deciding so is the engine's call: the loader reports it unchanged."""
        _serve_from(mocker=mocker, response=httpx.Response(200, content=CSS_BYTES, headers={"Content-Type": "application/octet-stream"}))

        loaded = await load_bytes_and_mime_type_from_any_uri(STYLESHEET_URL)

        assert loaded.mime_type == "application/octet-stream"

    @pytest.mark.parametrize(
        ("declared_type", "expected_mime_type"),
        [
            ("text/css", "text/css"),
            ("text/css;charset=utf-8", "text/css"),
            ("Image/SVG+XML", "image/svg+xml"),
            ("", None),
        ],
    )
    async def test_a_data_url_returns_the_type_it_declares(self, declared_type: str, expected_mime_type: str | None) -> None:
        loaded = await load_bytes_and_mime_type_from_any_uri(_data_url(declared_type=declared_type, body=CSS_BYTES))

        assert loaded == UriBytes(data=CSS_BYTES, mime_type=expected_mime_type)

    @pytest.mark.parametrize(
        ("recorded_type", "expected_mime_type"),
        [
            ("text/css", "text/css"),
            ("text/css; charset=UTF-8", "text/css"),
            (None, None),
        ],
    )
    async def test_a_storage_key_returns_the_type_the_provider_recorded(
        self, mocker: MockerFixture, recorded_type: str | None, expected_mime_type: str | None
    ) -> None:
        storage_uri = f"{PIPELEX_STORAGE_SCHEME}scope/assets/theme"
        load_with_metadata = mocker.AsyncMock(return_value=StoredData(data=CSS_BYTES, mime_type=recorded_type))
        storage_provider = mocker.MagicMock(spec=StorageProviderAbstract)
        storage_provider.load_with_metadata = load_with_metadata

        loaded = await load_bytes_and_mime_type_from_any_uri(storage_uri, storage_provider=storage_provider)

        assert loaded == UriBytes(data=CSS_BYTES, mime_type=expected_mime_type)
        load_with_metadata.assert_awaited_once_with(uri=storage_uri)

    async def test_a_storage_key_without_a_provider_is_refused(self) -> None:
        with pytest.raises(ValueError, match="without a storage provider"):
            await load_bytes_and_mime_type_from_any_uri(f"{PIPELEX_STORAGE_SCHEME}scope/assets/theme.css")

    async def test_a_local_path_returns_no_type(self, tmp_path: Path) -> None:
        """A file system records no type, and the loader does not read one off the file's name."""
        stylesheet_path = tmp_path / "theme.css"
        stylesheet_path.write_bytes(CSS_BYTES)

        loaded = await load_bytes_and_mime_type_from_any_uri(str(stylesheet_path))

        assert loaded == UriBytes(data=CSS_BYTES, mime_type=None)

    async def test_the_bytes_only_loader_returns_the_same_bytes(self, mocker: MockerFixture) -> None:
        _serve_from(mocker=mocker, response=httpx.Response(200, content=CSS_BYTES, headers={"Content-Type": "text/css"}))

        assert await load_bytes_from_any_uri(STYLESHEET_URL) == CSS_BYTES
