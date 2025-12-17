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
    def load(self, uri: str) -> bytes:
        """Load bytes from memory at the given URI.

        Args:
            uri: The URI key for the stored data.

        Returns:
            The stored bytes.

        Raises:
            StorageFileNotFoundError: If no data exists for the URI.
        """
        if uri not in self.root:
            msg = f"File not found: '{uri}'"
            raise StorageFileNotFoundError(msg)

        return self.root[uri]

    @override
    def store(self, data: bytes, uri: str) -> str:
        """Store bytes in memory at the given URI.

        Args:
            data: The bytes to store.
            uri: The URI key for storing the data.

        Returns:
            The URI of the stored data.
        """
        self.root[uri] = data
        log.debug(f"Stored data at URI: '{uri}'")
        return uri
