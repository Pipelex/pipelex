from pathlib import Path

import pytest

from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidUriError
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider


class TestLocalStorageProvider:
    """Unit tests for LocalStorageProvider."""

    def test_store_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Test storing bytes and loading them back returns the same data."""
        provider = LocalStorageProvider(root_path=tmp_path)
        test_data = b"Hello, World! \x00\x01\x02\xff"
        uri = "test_file.bin"

        returned_uri = provider.store(data=test_data, uri=uri)
        loaded_data = provider.load(uri=uri)

        assert returned_uri == uri
        assert loaded_data == test_data

    def test_store_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test that storing to a nested path creates intermediate directories."""
        provider = LocalStorageProvider(root_path=tmp_path)
        test_data = b"nested content"
        uri = "subdir/nested/deep/file.bin"

        provider.store(data=test_data, uri=uri)
        loaded_data = provider.load(uri=uri)

        assert loaded_data == test_data
        assert (tmp_path / "subdir" / "nested" / "deep" / "file.bin").exists()

    def test_load_nonexistent_file_raises_error(self, tmp_path: Path) -> None:
        """Test that loading a non-existent file raises StorageFileNotFoundError."""
        provider = LocalStorageProvider(root_path=tmp_path)

        with pytest.raises(StorageFileNotFoundError) as exc_info:
            provider.load(uri="nonexistent.bin")

        assert "nonexistent.bin" in str(exc_info.value)

    def test_store_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Test that storing to an existing path overwrites the file."""
        provider = LocalStorageProvider(root_path=tmp_path)
        uri = "overwrite_test.bin"
        original_data = b"original"
        new_data = b"updated content"

        provider.store(data=original_data, uri=uri)
        provider.store(data=new_data, uri=uri)
        loaded_data = provider.load(uri=uri)

        assert loaded_data == new_data

    def test_invalid_uri_with_path_traversal_raises_error(self, tmp_path: Path) -> None:
        """Test that URIs with path traversal (../) raise StorageInvalidUriError."""
        provider = LocalStorageProvider(root_path=tmp_path)

        with pytest.raises(StorageInvalidUriError) as exc_info:
            provider.store(data=b"malicious", uri="../outside.bin")

        assert "path traversal" in str(exc_info.value).lower()

    def test_load_invalid_uri_with_path_traversal_raises_error(self, tmp_path: Path) -> None:
        """Test that loading with path traversal URI raises StorageInvalidUriError."""
        provider = LocalStorageProvider(root_path=tmp_path)

        with pytest.raises(StorageInvalidUriError) as exc_info:
            provider.load(uri="../../etc/passwd")

        assert "path traversal" in str(exc_info.value).lower()

    def test_store_empty_bytes(self, tmp_path: Path) -> None:
        """Test storing and loading empty bytes."""
        provider = LocalStorageProvider(root_path=tmp_path)
        uri = "empty.bin"

        provider.store(data=b"", uri=uri)
        loaded_data = provider.load(uri=uri)

        assert loaded_data == b""

    def test_store_large_binary_data(self, tmp_path: Path) -> None:
        """Test storing and loading larger binary data."""
        provider = LocalStorageProvider(root_path=tmp_path)
        test_data = bytes(range(256)) * 1000  # ~256KB of data
        uri = "large_file.bin"

        provider.store(data=test_data, uri=uri)
        loaded_data = provider.load(uri=uri)

        assert loaded_data == test_data

    def test_absolute_uri_raises_error(self, tmp_path: Path) -> None:
        """Test that absolute URIs are rejected."""
        provider = LocalStorageProvider(root_path=tmp_path)

        with pytest.raises(StorageInvalidUriError) as exc_info:
            provider.store(data=b"test", uri="/absolute/path.bin")

        assert "absolute" in str(exc_info.value).lower()
