import pytest

from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidKeyError
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME


@pytest.mark.asyncio(loop_scope="class")
class TestInMemoryStorageProvider:
    """Unit tests for InMemoryStorageProvider with pipelex-storage:// URI scheme."""

    async def test_store_returns_uri_with_scheme(self) -> None:
        """Test that store() returns a URI with the pipelex-storage:// scheme prefix."""
        provider = InMemoryStorageProvider()
        test_data = b"Hello, World!"
        key = "test/file.bin"

        returned_uri = await provider.store(data=test_data, key=key)

        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"
        assert returned_uri.startswith(PIPELEX_STORAGE_SCHEME)

    async def test_load_with_valid_uri_returns_data(self) -> None:
        """Test roundtrip: store data with key, load with returned URI."""
        provider = InMemoryStorageProvider()
        test_data = b"Test data \x00\x01\x02\xff"
        key = "roundtrip/test.bin"

        returned_uri = await provider.store(data=test_data, key=key)
        loaded_data = await provider.load(uri=returned_uri)

        assert loaded_data == test_data

    async def test_load_with_invalid_uri_raises_error(self) -> None:
        """Test that loading a non-existent URI raises StorageFileNotFoundError."""
        provider = InMemoryStorageProvider()
        nonexistent_uri = f"{PIPELEX_STORAGE_SCHEME}nonexistent/file.bin"

        with pytest.raises(StorageFileNotFoundError) as exc_info:
            await provider.load(uri=nonexistent_uri)

        assert "nonexistent/file.bin" in str(exc_info.value)

    async def test_store_raises_if_key_has_scheme_prefix(self) -> None:
        """Test that passing a key with pipelex-storage:// prefix raises an error."""
        provider = InMemoryStorageProvider()
        invalid_key = f"{PIPELEX_STORAGE_SCHEME}already/prefixed.bin"

        with pytest.raises(StorageInvalidKeyError) as exc_info:
            await provider.store(data=b"test", key=invalid_key)

        assert "should not include scheme prefix" in str(exc_info.value).lower()

    async def test_public_url_returns_memory_reference(self) -> None:
        """Test that public_url() returns a human-readable memory reference."""
        provider = InMemoryStorageProvider()
        test_data = b"display test"
        key = "display/test.bin"

        returned_uri = await provider.store(data=test_data, key=key)
        display = await provider.public_url(uri=returned_uri)

        # Display should indicate it's in-memory storage
        assert display is None

    async def test_store_overwrites_existing_data(self) -> None:
        """Test that storing with the same key overwrites the previous data."""
        provider = InMemoryStorageProvider()
        key = "overwrite/test.bin"
        original_data = b"original"
        new_data = b"updated content"

        uri1 = await provider.store(data=original_data, key=key)
        uri2 = await provider.store(data=new_data, key=key)
        loaded_data = await provider.load(uri=uri2)

        assert uri1 == uri2
        assert loaded_data == new_data

    async def test_store_empty_bytes(self) -> None:
        """Test storing and loading empty bytes."""
        provider = InMemoryStorageProvider()
        key = "empty.bin"

        returned_uri = await provider.store(data=b"", key=key)
        loaded_data = await provider.load(uri=returned_uri)

        assert loaded_data == b""

    async def test_store_large_binary_data(self) -> None:
        """Test storing and loading larger binary data."""
        provider = InMemoryStorageProvider()
        test_data = bytes(range(256)) * 1000  # ~256KB of data
        key = "large_file.bin"

        returned_uri = await provider.store(data=test_data, key=key)
        loaded_data = await provider.load(uri=returned_uri)

        assert loaded_data == test_data

    async def test_multiple_keys_isolated(self) -> None:
        """Test that different keys store different data independently."""
        provider = InMemoryStorageProvider()
        data1 = b"first"
        data2 = b"second"
        key1 = "file1.bin"
        key2 = "file2.bin"

        uri1 = await provider.store(data=data1, key=key1)
        uri2 = await provider.store(data=data2, key=key2)

        assert await provider.load(uri=uri1) == data1
        assert await provider.load(uri=uri2) == data2

    async def test_metadata_round_trips_lowercase_and_follows_the_last_write(self) -> None:
        provider = InMemoryStorageProvider()
        uri = await provider.store(
            data=b"%PDF-", key="scope/report.docx.pdf", metadata={"Converter-Version": "0.1.0", "export-options": "printed-pages"}
        )

        assert await provider.load_metadata(uri=uri) == {"converter-version": "0.1.0", "export-options": "printed-pages"}

        await provider.store(data=b"%PDF- again", key="scope/report.docx.pdf")
        assert await provider.load_metadata(uri=uri) == {}

    async def test_store_if_absent_keeps_the_metadata_of_the_object_already_there(self) -> None:
        provider = InMemoryStorageProvider()
        assert await provider.store_if_absent(data=b"%PDF-", key="scope/report.docx.pdf", metadata={"converter-version": "0.1.0"}) is True
        assert await provider.store_if_absent(data=b"other", key="scope/report.docx.pdf", metadata={"converter-version": "9.9.9"}) is False

        assert await provider.load_metadata(uri=f"{PIPELEX_STORAGE_SCHEME}scope/report.docx.pdf") == {"converter-version": "0.1.0"}

    async def test_load_metadata_of_a_missing_object_raises_not_found(self) -> None:
        provider = InMemoryStorageProvider()

        with pytest.raises(StorageFileNotFoundError):
            await provider.load_metadata(uri=f"{PIPELEX_STORAGE_SCHEME}scope/missing.pdf")
