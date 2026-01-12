from abc import ABC, abstractmethod
from typing import NamedTuple

PIPELEX_STORAGE_SCHEME = "pipelex-storage://"


class StoredData(NamedTuple):
    """Data returned from storage with optional MIME type metadata."""

    data: bytes
    mime_type: str | None = None


class StorageProviderAbstract(ABC):
    """Abstract base class for storage providers.

    Provides common URI scheme handling (strip/add scheme) and defines
    the interface for concrete storage providers.

    Subclasses must implement:
        - _load_with_metadata(key): Load data with MIME type by key (without scheme)
        - _store(data, key, content_type): Store data and return URI
        - display_link(uri): Return human-readable link for URI
    """

    def _strip_scheme(self, uri: str) -> str:
        """Extract key from URI, raising error if invalid.

        Args:
            uri: Full URI including PIPELEX_STORAGE_SCHEME prefix.

        Returns:
            The key part without the scheme prefix.

        Raises:
            StorageFileNotFoundError: If URI doesn't start with the expected scheme.
        """
        from pipelex.tools.storage.exceptions import StorageFileNotFoundError  # noqa: PLC0415

        if not uri.startswith(PIPELEX_STORAGE_SCHEME):
            msg = f"Invalid URI '{uri}': must start with '{PIPELEX_STORAGE_SCHEME}'"
            raise StorageFileNotFoundError(msg)
        return uri.removeprefix(PIPELEX_STORAGE_SCHEME)

    def _add_scheme(self, key: str) -> str:
        """Build URI from key, raising error if key already has scheme.

        Args:
            key: Storage key without scheme prefix.

        Returns:
            Full URI with PIPELEX_STORAGE_SCHEME prefix.

        Raises:
            StorageInvalidKeyError: If key already contains the scheme prefix.
        """
        from pipelex.tools.storage.exceptions import StorageInvalidKeyError  # noqa: PLC0415

        if key.startswith(PIPELEX_STORAGE_SCHEME):
            msg = f"Key should not include scheme prefix: '{key}'"
            raise StorageInvalidKeyError(msg)
        return f"{PIPELEX_STORAGE_SCHEME}{key}"

    async def load(self, uri: str) -> bytes:
        """Load data from storage.

        Args:
            uri: Full URI including PIPELEX_STORAGE_SCHEME prefix.

        Returns:
            The stored bytes.
        """
        stored_data = await self.load_with_metadata(uri)
        return stored_data.data

    async def load_with_metadata(self, uri: str) -> StoredData:
        """Load data from storage with MIME type metadata.

        Args:
            uri: Full URI including PIPELEX_STORAGE_SCHEME prefix.

        Returns:
            StoredData containing bytes and optional MIME type.
        """
        key = self._strip_scheme(uri)
        return await self._load_with_metadata(key)

    @abstractmethod
    async def _load_with_metadata(self, key: str) -> StoredData:
        """Load data from storage by key with MIME type metadata.

        Args:
            key: Storage key (without scheme prefix).

        Returns:
            StoredData containing bytes and optional MIME type.
        """

    async def store(self, data: bytes, key: str, content_type: str | None = None) -> str:
        """Store data and return full URI with scheme.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the data (used by cloud providers).

        Returns:
            Full URI with PIPELEX_STORAGE_SCHEME prefix.
        """
        uri = self._add_scheme(key)
        await self._store(data=data, key=key, content_type=content_type)
        return uri

    @abstractmethod
    async def _store(self, data: bytes, *, key: str, content_type: str | None) -> None:
        """Store data in storage.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the data.
        """

    @abstractmethod
    async def display_link(self, uri: str) -> str | None:
        """Return human-readable link for this URI.

        Args:
            uri: Full URI including PIPELEX_STORAGE_SCHEME prefix.

        Returns:
            Human-readable link for debugging/display.
        """
