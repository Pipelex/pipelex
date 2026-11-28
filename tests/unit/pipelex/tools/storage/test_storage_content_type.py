import pytest

from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider

KEY = "scope/assets/one.txt"


@pytest.mark.asyncio(loop_scope="class")
class TestStorageContentType:
    @pytest.mark.parametrize(
        "content_type",
        [
            None,
            "text/plain",
            "application/pdf",
            "text/html; charset=utf-8",
            "text/markdown; charset=utf-8",
            'text/plain; charset="utf-8"',
            'multipart/form-data; boundary="a;b"',
            'text/plain; charset="a\\"b"',
            "text/plain; charset",
            "text/plain;",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
    )
    async def test_one_media_type_is_stored(self, content_type: str | None) -> None:
        """Every type the runtime writes passes, the parameters of a stored text's included."""
        storage = InMemoryStorageProvider()

        uri = await storage.store(data=b"hello", key=KEY, content_type=content_type)
        created = await storage.store_if_absent(data=b"hello", key="scope/assets/two.txt", content_type=content_type)

        assert await storage.load(uri) == b"hello"
        assert created is True

    @pytest.mark.parametrize(
        ("topic", "content_type"),
        [
            ("comma after a parameter", "application/pdf;,text/plain"),
            ("comma between types", "image/png,text/plain"),
            ("missing subtype", "text"),
            ("control character", "text/plain\n"),
            ("control character in the parameters", "text/plain; charset=utf-8\r"),
            ("parameters only", ";charset=utf-8"),
            ("blank", "   "),
            ("empty", ""),
        ],
    )
    async def test_a_type_that_is_not_one_media_type_is_refused_before_anything_is_stored(self, topic: str, content_type: str) -> None:
        storage = InMemoryStorageProvider()

        with pytest.raises(ValueError, match="is not one media type") as store_error:
            await storage.store(data=b"hello", key=KEY, content_type=content_type)
        with pytest.raises(ValueError, match="is not one media type"):
            await storage.store_if_absent(data=b"hello", key=KEY, content_type=content_type)

        assert KEY not in storage.root, topic
        if content_type:
            assert content_type not in str(store_error.value), topic
