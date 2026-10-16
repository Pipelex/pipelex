from pydantic import RootModel
from typing_extensions import override

from pipelex.tools.misc.exceptions import FileTypeError
from pipelex.tools.misc.filetype_utils import detect_file_type_from_bytes
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

        return StoredData(data=data, mime_type=mime_type)

    @override
    async def _load_size(self, key: str) -> int:
        """The length of the bytes held under `key`.

        Raises:
            StorageFileNotFoundError: If no data exists for the key.
        """
        if key not in self.root:
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg)
        return len(self.root[key])

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
    async def _store_if_absent(self, *, data: bytes, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> bool:
        """Hold the bytes under `key` unless it holds some already, never replacing them.

        Args:
            data: The bytes to store, already checked against their checksum.
            key: Storage key (without scheme prefix).
            content_type: Ignored for in-memory storage.
            checksum_sha256_hex: Checked before this call; memory has no checksum of its own to send it to.

        Returns:
            True when this call stored the bytes, False when the key already held some.
        """
        if key in self.root:
            return False
        self.root[key] = data
        return True

    @override
    async def public_url(self, uri: str) -> str | None:
        """In-memory storage cannot generate a public URL.

        Args:
            uri: Full URI including pipelex-storage:// scheme.

        Returns:
            None
        """
        return None
