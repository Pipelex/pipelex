import asyncio
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.tools.storage.exceptions import (
    StorageFileNotFoundError,
    StorageInvalidKeyError,
    StorageInvalidMetadataError,
    StorageInvalidUriError,
    StorageLocalError,
)
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

    async def test_key_with_null_byte_raises_invalid_uri(self, tmp_path: Path) -> None:
        """A key holding a NUL byte cannot name a file, so it is refused like any other invalid key.

        `Path.resolve()` raises a bare ValueError on it, which would otherwise escape a
        caller-supplied storage reference as an internal error.
        """
        provider = LocalStorageProvider(root_path=tmp_path)
        uri = f"{PIPELEX_STORAGE_SCHEME}a\x00b.png"

        with pytest.raises(StorageInvalidUriError, match="null byte"):
            await provider.public_url(uri=uri)
        with pytest.raises(StorageInvalidUriError, match="null byte"):
            await provider.load(uri=uri)

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

    async def test_store_wraps_oserror_as_storage_local_error(self, tmp_path: Path) -> None:
        """Test that an OSError during store is wrapped as StorageLocalError.

        A regular file blocks the parent-directory creation: mkdir(parents=True) on a
        path whose ancestor is a file raises FileExistsError (an OSError subclass).
        """
        provider = LocalStorageProvider(root_path=tmp_path)
        (tmp_path / "blocker").write_bytes(b"i am a file, not a directory")

        with pytest.raises(StorageLocalError) as exc_info:
            await provider.store(data=b"payload", key="blocker/foo.txt")

        assert "blocker/foo.txt" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, OSError)

    async def test_load_wraps_oserror_as_storage_local_error(self, tmp_path: Path) -> None:
        """Test that a non-not-found OSError during load is wrapped as StorageLocalError.

        Opening a directory as a file raises IsADirectoryError (an OSError subclass),
        which must surface as StorageLocalError rather than leaking raw.
        """
        provider = LocalStorageProvider(root_path=tmp_path)
        (tmp_path / "a_directory").mkdir()

        with pytest.raises(StorageLocalError) as exc_info:
            await provider.load(uri=f"{PIPELEX_STORAGE_SCHEME}a_directory")

        assert "a_directory" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, OSError)

    async def test_load_toctou_filenotfound_maps_to_not_found(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test that a FileNotFoundError raised after the exists() check maps to StorageFileNotFoundError.

        Simulates the TOCTOU window: the file passes exists() but is gone by the time
        open() runs. A missing file is a not-found, not a generic local-storage error.
        """
        provider = LocalStorageProvider(root_path=tmp_path)
        key = "toctou.bin"
        await provider.store(data=b"present at check time", key=key)

        mocker.patch(
            "pipelex.tools.storage.local_storage_provider.aiofiles.open",
            side_effect=FileNotFoundError(2, "No such file or directory"),
        )

        with pytest.raises(StorageFileNotFoundError) as exc_info:
            await provider.load(uri=f"{PIPELEX_STORAGE_SCHEME}{key}")

        assert key in str(exc_info.value)

    @pytest.mark.parametrize("held_before", [None, b"the bytes held before"])
    async def test_a_write_cut_short_leaves_the_key_as_it_was(self, tmp_path: Path, mocker: MockerFixture, held_before: bytes | None) -> None:
        """A write that fails midway, as on a full disk, publishes nothing: the key holds what it held, and no temporary file stays."""
        provider = LocalStorageProvider(root_path=tmp_path)
        key = "blobs/one.bin"
        if held_before is not None:
            await provider.store(data=held_before, key=key)
        real_replace = mocker.patch.object(Path, "replace", autospec=True, side_effect=OSError(28, "No space left on device"))

        with pytest.raises(StorageLocalError, match="No space left on device"):
            await provider.store(data=b"x" * 10_000, key=key)

        real_replace.assert_called_once()
        if held_before is None:
            assert not (tmp_path / key).exists()
        else:
            assert (tmp_path / key).read_bytes() == held_before
        assert sorted(path.name for path in (tmp_path / "blobs").iterdir()) == ([] if held_before is None else ["one.bin"])

    async def test_a_write_retried_after_a_failure_lands_whole(self, tmp_path: Path, mocker: MockerFixture) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)
        key = "blobs/one.bin"
        mocker.patch("pipelex.tools.storage.local_storage_provider.os.fsync", side_effect=OSError(5, "Input/output error"))
        with pytest.raises(StorageLocalError):
            await provider.store(data=b"payload", key=key)
        mocker.stopall()

        await provider.store(data=b"payload", key=key)

        assert (tmp_path / key).read_bytes() == b"payload"
        assert [path.name for path in (tmp_path / "blobs").iterdir()] == ["one.bin"]

    async def test_metadata_round_trips_through_a_hidden_sidecar(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)

        uri = await provider.store(
            data=b"%PDF-", key="scope/report.docx.pdf", metadata={"Converter-Version": "0.1.0", "export-options": "printed-pages"}
        )

        assert await provider.load_metadata(uri=uri) == {"converter-version": "0.1.0", "export-options": "printed-pages"}
        assert sorted(path.name for path in (tmp_path / "scope").iterdir()) == [".report.docx.pdf.metadata.json", "report.docx.pdf"]
        assert await provider.load(uri=uri) == b"%PDF-"

    async def test_a_file_stored_again_without_metadata_loses_its_sidecar(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)
        uri = await provider.store(data=b"%PDF-", key="scope/report.docx.pdf", metadata={"converter-version": "0.1.0"})

        await provider.store(data=b"%PDF- again", key="scope/report.docx.pdf")

        assert await provider.load_metadata(uri=uri) == {}
        assert [path.name for path in (tmp_path / "scope").iterdir()] == ["report.docx.pdf"]

    async def test_store_if_absent_writes_the_sidecar_only_with_the_file_it_creates(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)
        key = "scope/report.docx.pdf"

        assert await provider.store_if_absent(data=b"%PDF-", key=key, metadata={"converter-version": "0.1.0"}) is True
        assert await provider.store_if_absent(data=b"other", key=key, metadata={"converter-version": "9.9.9"}) is False

        assert await provider.load_metadata(uri=f"{PIPELEX_STORAGE_SCHEME}{key}") == {"converter-version": "0.1.0"}

    async def test_a_stale_sidecar_is_not_read_as_the_metadata_of_a_new_file(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)
        key = "scope/report.docx.pdf"
        await provider.store(data=b"%PDF-", key=key, metadata={"converter-version": "0.1.0"})
        (tmp_path / key).unlink()

        assert await provider.store_if_absent(data=b"%PDF- new", key=key) is True

        assert await provider.load_metadata(uri=f"{PIPELEX_STORAGE_SCHEME}{key}") == {}

    async def test_a_key_naming_a_sidecar_is_refused(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)

        with pytest.raises(StorageInvalidUriError, match="reserved"):
            await provider.store(data=b"{}", key="scope/.report.docx.pdf.metadata.json")
        with pytest.raises(StorageInvalidUriError, match="reserved"):
            await provider.load(uri=f"{PIPELEX_STORAGE_SCHEME}scope/.report.docx.pdf.metadata.json")

    async def test_load_metadata_of_a_missing_file_raises_not_found(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)

        with pytest.raises(StorageFileNotFoundError):
            await provider.load_metadata(uri=f"{PIPELEX_STORAGE_SCHEME}scope/missing.pdf")

    @staticmethod
    def _fail_sidecar_renames(*, mocker: MockerFixture) -> None:
        """Make every rename onto a sidecar fail, as a full or read-only directory would, and every other rename work."""
        real_replace = Path.replace

        def replace_unless_sidecar(self: Path, target: Path) -> Path:
            if Path(target).name.endswith(".metadata.json"):
                msg = "No space left on device"
                raise OSError(msg)
            return real_replace(self, target)

        mocker.patch.object(Path, "replace", autospec=True, side_effect=replace_unless_sidecar)

    async def test_a_store_whose_sidecar_cannot_be_published_leaves_no_file_without_its_metadata(self, tmp_path: Path, mocker: MockerFixture) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)
        key = "scope/report.docx.pdf"
        await provider.store(data=b"%PDF- old", key=key, metadata={"converter-version": "0.1.0"})
        self._fail_sidecar_renames(mocker=mocker)

        with pytest.raises(StorageLocalError):
            await provider.store(data=b"%PDF- new", key=key, metadata={"converter-version": "0.2.0"})

        # Neither the new bytes beside the old metadata, nor the new bytes without metadata: the key is empty.
        assert list((tmp_path / "scope").iterdir()) == []

    async def test_a_create_whose_sidecar_cannot_be_published_frees_the_key_for_the_next_attempt(self, tmp_path: Path, mocker: MockerFixture) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)
        key = "scope/report.docx.pdf"
        self._fail_sidecar_renames(mocker=mocker)

        with pytest.raises(StorageLocalError):
            await provider.store_if_absent(data=b"%PDF-", key=key, metadata={"converter-version": "0.1.0"})

        assert list((tmp_path / "scope").iterdir()) == []
        mocker.stopall()
        assert await provider.store_if_absent(data=b"%PDF-", key=key, metadata={"converter-version": "0.1.0"}) is True
        assert await provider.load_metadata(uri=f"{PIPELEX_STORAGE_SCHEME}{key}") == {"converter-version": "0.1.0"}

    async def test_writers_of_one_key_at_once_leave_bytes_beside_their_own_metadata(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)
        key = "scope/report.docx.pdf"
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"

        for _ in range(5):
            await asyncio.gather(
                *(
                    provider.store(data=f"%PDF- from writer {index_writer}".encode(), key=key, metadata={"writer": str(index_writer)})
                    for index_writer in range(12)
                )
            )
            stored = await provider.load(uri=uri)
            metadata = await provider.load_metadata(uri=uri)
            assert metadata is not None
            assert stored == f"%PDF- from writer {metadata['writer']}".encode()

    async def test_writers_of_one_key_on_several_threads_leave_bytes_beside_their_own_metadata(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)
        key = "scope/report.docx.pdf"
        uri = f"{PIPELEX_STORAGE_SCHEME}{key}"

        def store_from_a_thread(index_writer: int) -> None:
            for _ in range(20):
                asyncio.run(provider.store(data=f"%PDF- from writer {index_writer}".encode(), key=key, metadata={"writer": str(index_writer)}))

        await asyncio.gather(*(asyncio.to_thread(store_from_a_thread, index_writer) for index_writer in range(4)))

        metadata = await provider.load_metadata(uri=uri)
        assert metadata is not None
        assert await provider.load(uri=uri) == f"%PDF- from writer {metadata['writer']}".encode()

    async def test_metadata_that_is_not_ascii_is_refused_before_anything_is_stored(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)

        with pytest.raises(StorageInvalidMetadataError):
            await provider.store(data=b"%PDF-", key="scope/a.pdf", metadata={"converter-version": "0.1.0 \u2014 beta"})
        with pytest.raises(StorageInvalidMetadataError):
            await provider.store_if_absent(data=b"%PDF-", key="scope/b.pdf", metadata={"": "empty key"})

        assert not (tmp_path / "scope").exists()
