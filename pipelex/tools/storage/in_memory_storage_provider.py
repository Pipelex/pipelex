from pydantic import RootModel
from typing_extensions import override

from pipelex import log
from pipelex.tools.storage.exceptions import StorageFileNotFoundError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

InMemoryStorageRoot = dict[str, bytes]


class InMemoryStorageProvider(RootModel[InMemoryStorageRoot], StorageProviderAbstract):
    """In-memory storage provider using a dict mapping URIs to bytes."""

    root: InMemoryStorageRoot = {}

    @override
    async def _load(self, key: str) -> bytes:
        """Load bytes from memory.

        Args:
            key: Storage key (without scheme prefix).

        Returns:
            The stored bytes.

        Raises:
            StorageFileNotFoundError: If no data exists for the key.
        """
        if key not in self.root:
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg)

        log.dev(f"Loaded data from key: '{key}'")
        return self.root[key]

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
