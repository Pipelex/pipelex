from pathlib import Path

import aiofiles
from typing_extensions import override

from pipelex.tools.misc.filetype_utils import FileTypeError, detect_file_type_from_path
from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidUriError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract, StoredData


class LocalStorageProvider(StorageProviderAbstract):
    """Storage provider implementation for local filesystem storage.

    Files are stored relative to a root path, with keys being relative path strings.
    """

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
            StorageInvalidUriError: If the key is invalid (absolute path or path traversal).
        """
        relative_path = Path(key)

        if relative_path.is_absolute():
            msg = f"Invalid key '{key}': absolute paths are not allowed"
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
        """
        file_path = self._validate_key(key)

        if not file_path.exists():
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg)

        async with aiofiles.open(file_path, "rb") as file_handle:  # pyright: ignore[reportUnknownMemberType]
            data = await file_handle.read()

        # Detect MIME type from file path
        mime_type: str | None = None
        try:
            file_type = detect_file_type_from_path(file_path)
            mime_type = file_type.mime
        except FileTypeError:
            pass  # MIME type detection failed, return None

        return StoredData(data=data, mime_type=mime_type)

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None) -> None:
        """Store bytes to a file.

        Args:
            data: The bytes to store.
            key: Storage key (relative path, without scheme prefix).
            content_type: Ignored for local storage.

        Raises:
            StorageInvalidUriError: If the key is invalid.
        """
        file_path = self._validate_key(key)

        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(file_path, "wb") as file_handle:  # pyright: ignore[reportUnknownMemberType]
            await file_handle.write(data)

    @override
    async def display_link(self, uri: str) -> str:
        """Return a file:// URI for this storage URI.

        Args:
            uri: Full URI including pipelex-storage:// scheme.

        Returns:
            file:// URI that can be clicked in terminals like Cursor.
        """
        key = self._strip_scheme(uri)
        file_path = self._validate_key(key)
        return file_path.as_uri()
