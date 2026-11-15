import base64

import pytest

from pipelex.tools.storage.exceptions import StorageNotConfiguredError
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.uri.exceptions import UriReadRefusalReason, UriReadRefusedError, UriTextNotUtf8Error
from pipelex.tools.uri.uri_text import load_text_from_any_uri

READ_SCOPE = "org_abc"
KEY = "org_abc/mt_1/run_9/generated/0123abcd/text.txt"
TEXT = "Un texte stocké, accents compris."


def _storage() -> InMemoryStorageProvider:
    storage = InMemoryStorageProvider()
    storage.root[KEY] = TEXT.encode("utf-8")
    return storage


@pytest.mark.asyncio(loop_scope="class")
class TestLoadTextFromAnyUri:
    async def test_a_storage_key_under_the_read_scope_is_read_as_utf8(self) -> None:
        text = await load_text_from_any_uri(f"pipelex-storage://{KEY}", read_scope=READ_SCOPE, position="a text", storage_provider=_storage())
        assert text == TEXT

    async def test_a_data_url_is_read_without_storage(self) -> None:
        data_url = f"data:text/plain;base64,{base64.b64encode(TEXT.encode('utf-8')).decode('ascii')}"
        text = await load_text_from_any_uri(data_url, read_scope=READ_SCOPE, position="a text")
        assert text == TEXT

    @pytest.mark.parametrize(
        ("uri", "expected_reason"),
        [
            ("pipelex-storage://org_other/mt_1/run_9/generated/0123abcd/text.txt", UriReadRefusalReason.FOREIGN_STORAGE_KEY),
            ("/etc/passwd", UriReadRefusalReason.LOCAL_PATH),
        ],
    )
    async def test_a_url_outside_the_read_scope_is_refused_before_any_read(self, uri: str, expected_reason: UriReadRefusalReason) -> None:
        with pytest.raises(UriReadRefusedError) as exc_info:
            await load_text_from_any_uri(uri, read_scope=READ_SCOPE, position="the text input 'pages'", storage_provider=_storage())
        assert exc_info.value.reason == expected_reason
        assert "the text input 'pages'" in str(exc_info.value)

    async def test_a_storage_key_without_a_provider_is_refused(self) -> None:
        with pytest.raises(StorageNotConfiguredError):
            await load_text_from_any_uri(f"pipelex-storage://{KEY}", read_scope=None, position="a text")

    async def test_bytes_that_are_not_utf8_are_refused(self) -> None:
        storage = InMemoryStorageProvider()
        storage.root[KEY] = b"\xff\xfe\xfa"
        with pytest.raises(UriTextNotUtf8Error) as exc_info:
            await load_text_from_any_uri(
                f"pipelex-storage://{KEY}", read_scope=READ_SCOPE, position="the text input 'pages'", storage_provider=storage
            )
        assert "the text input 'pages'" in str(exc_info.value)
