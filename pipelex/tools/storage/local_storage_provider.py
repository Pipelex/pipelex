import contextlib
import os
from pathlib import Path
from typing import ClassVar
from uuid import uuid4

import aiofiles
from typing_extensions import override

from pipelex.tools.misc.exceptions import FileTypeError
from pipelex.tools.misc.filetype_utils import detect_file_type_from_path
from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidUriError, StorageLocalError
from pipelex.tools.storage.storage_provider_abstract import StorageKind, StorageProviderAbstract, StoredData


class LocalStorageProvider(StorageProviderAbstract):
    """Storage provider implementation for local filesystem storage.

    Files are stored relative to a root path, with keys being relative path strings.
    """

    storage_kind: ClassVar[StorageKind] = "local"

    def __init__(self, root_path: Path) -> None:
        """Initialize the local storage provider.

        Args:
            root_path: The base directory for all storage operations.
        """
        self._root_path = root_path

    def _validate_key(self, key: str) -> Path:
        """Validate the key and return the resolved absolute path.

        Args:
            key: The relative path key to validate.

        Returns:
            The resolved absolute path.

        Raises:
            StorageInvalidUriError: If the key is invalid (a NUL byte, an absolute path or path traversal).
        """
        relative_path = Path(key)

        if relative_path.is_absolute():
            msg = f"Invalid key '{key}': absolute paths are not allowed"
            raise StorageInvalidUriError(msg)

        # A NUL byte cannot name a file, and resolve() rejects it with a bare ValueError
        if "\x00" in key:
            msg = f"Invalid key {key!r}: a null byte is not allowed"
            raise StorageInvalidUriError(msg)

        resolved_path = (self._root_path / relative_path).resolve()

        # Check for path traversal attempts
        try:
            resolved_path.relative_to(self._root_path.resolve())
        except ValueError as exc:
            msg = f"Invalid key '{key}': path traversal is not allowed"
            raise StorageInvalidUriError(msg) from exc

        return resolved_path

    @override
    async def _load_with_metadata(self, key: str) -> StoredData:
        """Load bytes from a file with MIME type metadata.

        Args:
            key: Storage key (relative path, without scheme prefix).

        Returns:
            StoredData containing file contents and detected MIME type.

        Raises:
            StorageFileNotFoundError: If the file does not exist.
            StorageInvalidUriError: If the key is invalid.
            StorageLocalError: If the filesystem read fails (e.g. permission denied, I/O error).
        """
        file_path = self._validate_key(key)

        if not file_path.exists():
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind)

        try:
            async with aiofiles.open(file_path, "rb") as file_handle:  # pyright: ignore[reportUnknownMemberType]
                data = await file_handle.read()
        except FileNotFoundError as exc:
            # TOCTOU: the file passed exists() above but was removed before the open.
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind) from exc
        except OSError as exc:
            msg = f"Failed to read file '{key}': {exc}"
            raise StorageLocalError(msg) from exc

        # Detect MIME type from file path
        mime_type: str | None = None
        try:
            file_type = detect_file_type_from_path(file_path)
            mime_type = file_type.mime
        except FileTypeError:
            pass  # MIME type detection failed, return None

        return StoredData(data=data, mime_type=mime_type)

    @override
    async def _load_size(self, key: str) -> int:
        """The size of a file, read from its metadata without opening it.

        Raises:
            StorageFileNotFoundError: If the file does not exist.
            StorageInvalidUriError: If the key is invalid.
            StorageLocalError: If the key names something that is not a file, or the filesystem cannot stat it.
        """
        file_path = self._validate_key(key)
        try:
            stat_result = file_path.stat()
        except FileNotFoundError as exc:
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind) from exc
        except OSError as exc:
            msg = f"Failed to read the size of file '{key}': {exc}"
            raise StorageLocalError(msg) from exc
        if not file_path.is_file():
            msg = f"Failed to read the size of '{key}': it is not a file"
            raise StorageLocalError(msg)
        return stat_result.st_size

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None) -> None:
        """Store bytes to a file, published whole or not at all.

        The bytes are written to a temporary file beside the target, flushed to disk, then renamed onto the target,
        which is atomic within one filesystem: a reader, or a process checking whether the key exists, never sees a
        file a full disk or a killed process cut short. Two writers of one key each write their own temporary file,
        and the last rename wins whole.

        Args:
            data: The bytes to store.
            key: Storage key (relative path, without scheme prefix).
            content_type: Ignored for local storage.

        Raises:
            StorageInvalidUriError: If the key is invalid.
            StorageLocalError: If the filesystem write fails (e.g. disk full, permission denied).
        """
        file_path = self._validate_key(key)
        temporary_path = file_path.with_name(f".{file_path.name}.{uuid4().hex}.tmp")

        try:
            # Create parent directories if they don't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(temporary_path, "wb") as file_handle:  # pyright: ignore[reportUnknownMemberType]
                await file_handle.write(data)
                await file_handle.flush()
                os.fsync(file_handle.fileno())
            temporary_path.replace(file_path)
        except OSError as exc:
            msg = f"Failed to write file '{key}': {exc}"
            raise StorageLocalError(msg) from exc
        finally:
            # Gone once renamed; a write that failed leaves it behind, and removing it is best effort.
            with contextlib.suppress(OSError):
                temporary_path.unlink(missing_ok=True)

    @override
    async def public_url(self, uri: str) -> str:
        """Return a file:// URI for this storage URI.

        Args:
            uri: Full URI including pipelex-storage:// scheme.

        Returns:
            file:// URI that can be clicked in terminals like Cursor.
        """
        key = self._strip_scheme(uri)
        file_path = self._validate_key(key)
        return file_path.as_uri()
