from collections.abc import Mapping
from typing import ClassVar

from pydantic import PrivateAttr, RootModel
from typing_extensions import override

from pipelex.tools.misc.exceptions import FileTypeError
from pipelex.tools.misc.filetype_utils import detect_file_type_from_bytes
from pipelex.tools.storage.exceptions import StorageFileNotFoundError
from pipelex.tools.storage.storage_provider_abstract import StorageKind, StorageProviderAbstract, StoredData

InMemoryStorageRoot = dict[str, bytes]


class InMemoryStorageProvider(RootModel[InMemoryStorageRoot], StorageProviderAbstract):
    """In-memory storage provider using a dict mapping URIs to bytes, and a second one for the metadata kept beside them."""

    storage_kind: ClassVar[StorageKind] = "memory"

    root: InMemoryStorageRoot = {}
    # The metadata of each key stored with some, keys lowercase; a key stored with none has no entry.
    _metadata_by_key: dict[str, dict[str, str]] = PrivateAttr(default_factory=dict)

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
            raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind)

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
            raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind)
        return len(self.root[key])

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> None:
        """Store bytes in memory, with no metadata.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Ignored for in-memory storage.
            checksum_sha256_hex: Ignored: memory has no checksum of its own to send it to.
        """
        await self._store_with_metadata(data=data, key=key, content_type=content_type, checksum_sha256_hex=checksum_sha256_hex, metadata=None)

    @override
    async def _store_with_metadata(
        self,
        *,
        data: bytes,
        key: str,
        content_type: str | None,
        checksum_sha256_hex: str | None,
        metadata: Mapping[str, str] | None,
    ) -> None:
        """Store bytes in memory, and the metadata kept beside them, replacing what the key held.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Ignored for in-memory storage.
            checksum_sha256_hex: Ignored: memory has no checksum of its own to send it to.
            metadata: String pairs to keep beside the bytes, or None for none.
        """
        self.root[key] = data
        self._keep_metadata(key=key, metadata=metadata)

    @override
    async def _store_if_absent(self, *, data: bytes, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> bool:
        """Hold the bytes under `key` unless it holds some already, never replacing them, with no metadata.

        Args:
            data: The bytes to store, already checked against their checksum.
            key: Storage key (without scheme prefix).
            content_type: Ignored for in-memory storage.
            checksum_sha256_hex: Checked before this call; memory has no checksum of its own to send it to.

        Returns:
            True when this call stored the bytes, False when the key already held some.
        """
        return await self._store_if_absent_with_metadata(
            data=data, key=key, content_type=content_type, checksum_sha256_hex=checksum_sha256_hex, metadata=None
        )

    @override
    async def _store_if_absent_with_metadata(
        self,
        *,
        data: bytes,
        key: str,
        content_type: str | None,
        checksum_sha256_hex: str | None,
        metadata: Mapping[str, str] | None,
    ) -> bool:
        """Hold the bytes and their metadata under `key` unless it holds some already, never replacing them.

        Args:
            data: The bytes to store, already checked against their checksum.
            key: Storage key (without scheme prefix).
            content_type: Ignored for in-memory storage.
            checksum_sha256_hex: Checked before this call; memory has no checksum of its own to send it to.
            metadata: String pairs to keep beside the bytes this call stores, or None for none.

        Returns:
            True when this call stored the bytes, False when the key already held some.
        """
        if key in self.root:
            return False
        self.root[key] = data
        self._keep_metadata(key=key, metadata=metadata)
        return True

    def _keep_metadata(self, *, key: str, metadata: Mapping[str, str] | None) -> None:
        if metadata:
            self._metadata_by_key[key] = {meta_key.lower(): meta_value for meta_key, meta_value in metadata.items()}
        else:
            self._metadata_by_key.pop(key, None)

    @override
    async def _load_metadata(self, key: str) -> Mapping[str, str]:
        """The metadata kept beside the bytes under `key`, empty when they were stored with none.

        Raises:
            StorageFileNotFoundError: If no data exists for the key.
        """
        if key not in self.root:
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind)
        return dict(self._metadata_by_key.get(key, {}))

    @override
    async def public_url(self, uri: str) -> str | None:
        """In-memory storage cannot generate a public URL.

        Args:
            uri: Full URI including pipelex-storage:// scheme.

        Returns:
            None
        """
        return None
