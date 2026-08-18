import pytest

from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageProviderAbstract


@pytest.mark.asyncio(loop_scope="class")
class TestStorageProviders:
    """Integration tests for both Local and InMemory storage providers."""

    async def test_store_and_load_roundtrip(self, storage_provider: StorageProviderAbstract) -> None:
        """Test that data can be stored and loaded correctly."""
        test_data = b"Hello, World! \x00\x01\x02\xff"
        key = "test/roundtrip.bin"

        returned_uri = await storage_provider.store(data=test_data, key=key)
        loaded_data = await storage_provider.load(uri=returned_uri)

        assert loaded_data == test_data
        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"

    async def test_uri_format_from_config(
        self,
        storage_provider: StorageProviderAbstract,
        uri_format: str,
    ) -> None:
        """Test that the URI format from config works correctly for building storage keys."""
        test_data = b"config format test"
        primary_id = "pipeline_123"
        secondary_id = "step_456"
        hash_value = "abc123def456"
        extension = "png"

        key = uri_format.format(
            storage_scope="test/scope",
            hash=hash_value,
            extension=extension,
        )

        returned_uri = await storage_provider.store(data=test_data, key=key)
        loaded_data = await storage_provider.load(uri=returned_uri)

        assert loaded_data == test_data
        assert primary_id in key
        assert secondary_id in key
        assert hash_value in key
        assert extension in key

    async def test_store_binary_image_data(self, storage_provider: StorageProviderAbstract) -> None:
        """Test storing and retrieving binary image data (PNG header)."""
        png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        key = "images/test_image.png"

        returned_uri = await storage_provider.store(data=png_header, key=key)
        loaded_data = await storage_provider.load(uri=returned_uri)

        assert loaded_data == png_header
        assert loaded_data[:8] == b"\x89PNG\r\n\x1a\n"

    async def test_store_multiple_files_isolated(self, storage_provider: StorageProviderAbstract) -> None:
        """Test that multiple files are stored and retrieved independently."""
        data1 = b"first file content"
        data2 = b"second file content"
        data3 = b"third file content"

        uri1 = await storage_provider.store(data=data1, key="multi/file1.bin")
        uri2 = await storage_provider.store(data=data2, key="multi/file2.bin")
        uri3 = await storage_provider.store(data=data3, key="multi/file3.bin")

        assert await storage_provider.load(uri=uri1) == data1
        assert await storage_provider.load(uri=uri2) == data2
        assert await storage_provider.load(uri=uri3) == data3

    async def test_store_with_nested_path(self, storage_provider: StorageProviderAbstract) -> None:
        """Test storing data in a deeply nested path structure."""
        test_data = b"nested content"
        key = "level1/level2/level3/deep_file.bin"

        returned_uri = await storage_provider.store(data=test_data, key=key)
        loaded_data = await storage_provider.load(uri=returned_uri)

        assert loaded_data == test_data

    async def test_store_empty_bytes(self, storage_provider: StorageProviderAbstract) -> None:
        """Test storing and loading empty bytes."""
        key = "empty/file.bin"

        returned_uri = await storage_provider.store(data=b"", key=key)
        loaded_data = await storage_provider.load(uri=returned_uri)

        assert loaded_data == b""

    async def test_store_large_binary_data(self, storage_provider: StorageProviderAbstract) -> None:
        """Test storing and loading larger binary data (~256KB)."""
        test_data = bytes(range(256)) * 1000
        key = "large/file.bin"

        returned_uri = await storage_provider.store(data=test_data, key=key)
        loaded_data = await storage_provider.load(uri=returned_uri)

        assert loaded_data == test_data
        assert len(loaded_data) == len(test_data)

    async def test_overwrite_existing_data(self, storage_provider: StorageProviderAbstract) -> None:
        """Test that storing with the same key overwrites the previous data."""
        key = "overwrite/test.bin"
        original_data = b"original"
        updated_data = b"updated content"

        await storage_provider.store(data=original_data, key=key)
        returned_uri = await storage_provider.store(data=updated_data, key=key)
        loaded_data = await storage_provider.load(uri=returned_uri)

        assert loaded_data == updated_data

    async def test_public_url_returns_value_or_none(self, storage_provider: StorageProviderAbstract) -> None:
        """Test that public_url returns either a valid link or None."""
        test_data = b"display link test"
        key = "display/test.bin"

        returned_uri = await storage_provider.store(data=test_data, key=key)
        display = await storage_provider.public_url(uri=returned_uri)

        # public_url can return None (in-memory) or a string (local file://)
        if display is not None:
            assert isinstance(display, str)
            assert len(display) > 0
