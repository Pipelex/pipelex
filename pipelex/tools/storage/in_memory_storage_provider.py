from pydantic import RootModel
from typing_extensions import override

from pipelex import log
from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidKeyError
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageProviderAbstract

InMemoryStorageRoot = dict[str, bytes]


class InMemoryStorageProvider(RootModel[InMemoryStorageRoot], StorageProviderAbstract):
    """In-memory storage provider using a dict mapping URIs to bytes."""

    root: InMemoryStorageRoot = {}

    def _strip_scheme(self, uri: str) -> str:
        """Extract key from URI, raising error if invalid."""
        if not uri.startswith(PIPELEX_STORAGE_SCHEME):
            msg = f"Invalid URI '{uri}': must start with '{PIPELEX_STORAGE_SCHEME}'"
            raise StorageFileNotFoundError(msg)
        return uri.removeprefix(PIPELEX_STORAGE_SCHEME)

    def _add_scheme(self, key: str) -> str:
        """Build URI from key, raising error if key already has scheme."""
        if key.startswith(PIPELEX_STORAGE_SCHEME):
            msg = f"Key should not include scheme prefix: '{key}'"
            raise StorageInvalidKeyError(msg)
        return f"{PIPELEX_STORAGE_SCHEME}{key}"

    @override
    def load(self, uri: str) -> bytes:
        """Load bytes from memory at the given URI.

        Args:
            uri: Full URI including PIPELEX_STORAGE_SCHEME prefix.

        Returns:
            The stored bytes.

        Raises:
            StorageFileNotFoundError: If no data exists for the URI.
        """
        key = self._strip_scheme(uri)
        if key not in self.root:
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg)

        log.dev(f"Loaded data from URI: '{uri}'")
        return self.root[key]

    @override
    def store(self, data: bytes, key: str) -> str:
        """Store bytes in memory.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).

        Returns:
            Full URI with pipelex-storage:// scheme.
        """
        uri = self._add_scheme(key)
        self.root[key] = data
        return uri

    @override
    def display_link(self, uri: str) -> str | None:
        """In-memory storage cannot generate a display link.

        Args:
            uri: Full URI including pipelex-storage:// scheme.

        Returns:
            None
        """
        return None
