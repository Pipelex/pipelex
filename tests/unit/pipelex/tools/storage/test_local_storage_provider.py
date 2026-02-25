from pathlib import Path

import pytest

from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidKeyError, StorageInvalidUriError
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME


@pytest.mark.asyncio(loop_scope="class")
class TestLocalStorageProvider:
    """Unit tests for LocalStorageProvider with pipelex-storage:// URI scheme."""

    async def test_store_returns_uri_with_scheme(self, tmp_path: Path) -> None:
        """Test that store() returns a URI with the pipelex-storage:// scheme prefix."""
        provider = LocalStorageProvider(root_path=tmp_path)
        test_data = b"Hello, World!"
        key = "test_file.bin"

        returned_uri = await provider.store(data=test_data, key=key)

        assert returned_uri == f"{PIPELEX_STORAGE_SCHEME}{key}"
        assert returned_uri.startswith(PIPELEX_STORAGE_SCHEME)

    async def test_load_with_valid_uri_returns_data(self, tmp_path: Path) -> None:
        """Test roundtrip: store data with key, load with returned URI."""
        provider = LocalStorageProvider(root_path=tmp_path)
        test_data = b"Hello, World! \x00\x01\x02\xff"
        key = "test_file.bin"

        returned_uri = await provider.store(data=test_data, key=key)
        loaded_data = await provider.load(uri=returned_uri)

        assert loaded_data == test_data

    async def test_load_with_invalid_uri_raises_error(self, tmp_path: Path) -> None:
        """Test that loading a non-existent URI raises StorageFileNotFoundError."""
        provider = LocalStorageProvider(root_path=tmp_path)
        nonexistent_uri = f"{PIPELEX_STORAGE_SCHEME}nonexistent.bin"

        with pytest.raises(StorageFileNotFoundError) as exc_info:
            await provider.load(uri=nonexistent_uri)

        assert "nonexistent.bin" in str(exc_info.value)

    async def test_store_raises_if_key_has_scheme_prefix(self, tmp_path: Path) -> None:
        """Test that passing a key with pipelex-storage:// prefix raises an error."""
        provider = LocalStorageProvider(root_path=tmp_path)
        invalid_key = f"{PIPELEX_STORAGE_SCHEME}already/prefixed.bin"

        with pytest.raises(StorageInvalidKeyError) as exc_info:
            await provider.store(data=b"test", key=invalid_key)

        assert "should not include scheme prefix" in str(exc_info.value).lower()

    async def test_public_url_returns_file_uri(self, tmp_path: Path) -> None:
        """Test that public_url() returns a file:// URI for clickable terminal links."""
        provider = LocalStorageProvider(root_path=tmp_path)
        test_data = b"display test"
        key = "subdir/display_test.bin"

        returned_uri = await provider.store(data=test_data, key=key)
        display = await provider.public_url(uri=returned_uri)

        expected_uri = (tmp_path / key).as_uri()
        assert display == expected_uri
        assert display.startswith("file://")

    async def test_store_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test that storing to a nested path creates intermediate directories."""
        provider = LocalStorageProvider(root_path=tmp_path)
        test_data = b"nested content"
        key = "subdir/nested/deep/file.bin"

        returned_uri = await provider.store(data=test_data, key=key)
        loaded_data = await provider.load(uri=returned_uri)

        assert loaded_data == test_data
        assert (tmp_path / "subdir" / "nested" / "deep" / "file.bin").exists()

    async def test_store_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Test that storing with the same key overwrites the file."""
        provider = LocalStorageProvider(root_path=tmp_path)
        key = "overwrite_test.bin"
        original_data = b"original"
        new_data = b"updated content"

        await provider.store(data=original_data, key=key)
        returned_uri = await provider.store(data=new_data, key=key)
        loaded_data = await provider.load(uri=returned_uri)

        assert loaded_data == new_data

    async def test_invalid_key_with_path_traversal_raises_error(self, tmp_path: Path) -> None:
        """Test that keys with path traversal (../) raise StorageInvalidUriError."""
        provider = LocalStorageProvider(root_path=tmp_path)

        with pytest.raises(StorageInvalidUriError) as exc_info:
            await provider.store(data=b"malicious", key="../outside.bin")

        assert "path traversal" in str(exc_info.value).lower()

    async def test_load_with_path_traversal_key_raises_error(self, tmp_path: Path) -> None:
        """Test that loading with path traversal in URI raises StorageInvalidUriError."""
        provider = LocalStorageProvider(root_path=tmp_path)
        # Manually construct a URI with path traversal (bypassing store validation)
        malicious_uri = f"{PIPELEX_STORAGE_SCHEME}../../etc/passwd"

        with pytest.raises(StorageInvalidUriError) as exc_info:
            await provider.load(uri=malicious_uri)

        assert "path traversal" in str(exc_info.value).lower()

    async def test_store_empty_bytes(self, tmp_path: Path) -> None:
        """Test storing and loading empty bytes."""
        provider = LocalStorageProvider(root_path=tmp_path)
        key = "empty.bin"

        returned_uri = await provider.store(data=b"", key=key)
        loaded_data = await provider.load(uri=returned_uri)

        assert loaded_data == b""

    async def test_store_large_binary_data(self, tmp_path: Path) -> None:
        """Test storing and loading larger binary data."""
        provider = LocalStorageProvider(root_path=tmp_path)
        test_data = bytes(range(256)) * 1000  # ~256KB of data
        key = "large_file.bin"

        returned_uri = await provider.store(data=test_data, key=key)
        loaded_data = await provider.load(uri=returned_uri)

        assert loaded_data == test_data

    async def test_absolute_key_raises_error(self, tmp_path: Path) -> None:
        """Test that absolute paths as keys are rejected."""
        provider = LocalStorageProvider(root_path=tmp_path)

        with pytest.raises(StorageInvalidUriError) as exc_info:
            await provider.store(data=b"test", key="/absolute/path.bin")

        assert "absolute" in str(exc_info.value).lower()

    async def test_file_actually_written_to_disk(self, tmp_path: Path) -> None:
        """Test that the file is actually written to the filesystem."""
        provider = LocalStorageProvider(root_path=tmp_path)
        test_data = b"disk content"
        key = "on_disk.bin"

        await provider.store(data=test_data, key=key)

        file_path = tmp_path / key
        assert file_path.exists()
        assert file_path.read_bytes() == test_data
