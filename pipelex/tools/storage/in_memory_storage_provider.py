from pydantic import RootModel
from typing_extensions import override

from pipelex import log
from pipelex.tools.misc.filetype_utils import FileTypeError, detect_file_type_from_bytes
from pipelex.tools.storage.exceptions import StorageFileNotFoundError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract, StoredData

InMemoryStorageRoot = dict[str, bytes]


class InMemoryStorageProvider(RootModel[InMemoryStorageRoot], StorageProviderAbstract):
    """In-memory storage provider using a dict mapping URIs to bytes."""

    root: InMemoryStorageRoot = {}

    @override
    async def _load_with_metadata(self, key: str) -> StoredData:
        """Load bytes from memory with MIME type metadata.

        Args:
            key: Storage key (without scheme prefix).

        Returns:
            StoredData containing bytes and detected MIME type.

        Raises:
            StorageFileNotFoundError: If no data exists for the key.
        """
        if key not in self.root:
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg)

        data = self.root[key]

        # Detect MIME type from bytes
        mime_type: str | None = None
        try:
            file_type = detect_file_type_from_bytes(data)
            mime_type = file_type.mime
        except FileTypeError:
            pass  # MIME type detection failed, return None

        log.dev(f"Loaded data with metadata from key: '{key}', mime_type={mime_type}")
        return StoredData(data=data, mime_type=mime_type)

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None) -> None:
        """Store bytes in memory.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Ignored for in-memory storage.
        """
        self.root[key] = data

    @override
    async def display_link(self, uri: str) -> str | None:
        """In-memory storage cannot generate a display link.

        Args:
            uri: Full URI including pipelex-storage:// scheme.

        Returns:
            None
        """
        return None
