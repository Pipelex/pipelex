from abc import ABC, abstractmethod
from typing import ClassVar, Literal, NamedTuple

from mthds.protocol.problem.registry import CoreCode

from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidKeyError

PIPELEX_STORAGE_SCHEME = "pipelex-storage://"

# The kind of storage a provider is, as the `scheme` parameter of the `pipelex.storage.*` codes names it: one Pipelex
# ships, or `plugin` for a storage plugin's own.
StorageKind = Literal["local", "s3", "gcs", "memory", "plugin"]


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
        - public_url(uri): Return human-readable link for URI

    A provider Pipelex ships names its kind in ``storage_kind``, the ``scheme`` its refusals carry; a plugin's provider
    keeps the default, ``plugin``.
    """

    storage_kind: ClassVar[StorageKind] = "plugin"

    def _strip_scheme(self, uri: str) -> str:
        """Extract key from URI, raising error if invalid.

        Args:
            uri: Full URI including PIPELEX_STORAGE_SCHEME prefix.

        Returns:
            The key part without the scheme prefix.

        Raises:
            StorageFileNotFoundError: If URI doesn't start with the expected scheme.
        """
        if not uri.startswith(PIPELEX_STORAGE_SCHEME):
            # A URI of another scheme reaching this provider is a routing fault of the runtime, not a missing file.
            msg = f"Invalid URI '{uri}': must start with '{PIPELEX_STORAGE_SCHEME}'"
            raise StorageFileNotFoundError(msg).with_error_code(CoreCode.RUNTIME_UNEXPECTED)
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

    async def load_head(self, uri: str, *, nb_bytes: int) -> bytes:
        """Load the first bytes of a stored object, which is all identifying its format needs.

        Args:
            uri: Full URI including PIPELEX_STORAGE_SCHEME prefix.
            nb_bytes: How many leading bytes to read. An object shorter than this is read whole.

        Returns:
            At most `nb_bytes` leading bytes of the object.
        """
        key = self._strip_scheme(uri)
        return await self._load_head(key, nb_bytes=nb_bytes)

    async def _load_head(self, key: str, *, nb_bytes: int) -> bytes:
        """Load the first bytes of an object by key.

        This default loads the whole object and slices it, so a provider that cannot read a byte
        range, an external storage plugin included, keeps working unchanged. A provider that can
        read a range overrides it.

        Args:
            key: Storage key (without scheme prefix).
            nb_bytes: How many leading bytes to read.

        Returns:
            At most `nb_bytes` leading bytes of the object.
        """
        stored_data = await self._load_with_metadata(key)
        return stored_data.data[:nb_bytes]

    async def load_size(self, uri: str) -> int:
        """The size of a stored object in bytes, read without its bytes where the provider can.

        Args:
            uri: Full URI including PIPELEX_STORAGE_SCHEME prefix.

        Returns:
            The object's length in bytes.
        """
        key = self._strip_scheme(uri)
        return await self._load_size(key)

    async def _load_size(self, key: str) -> int:
        """The size of an object by key.

        This default loads the whole object and measures it, so a provider that cannot read an object's
        metadata alone, an external storage plugin included, keeps working unchanged. A provider that can
        overrides it, and a caller bounding what it reads relies on that override.

        Args:
            key: Storage key (without scheme prefix).

        Returns:
            The object's length in bytes.
        """
        stored_data = await self._load_with_metadata(key)
        return len(stored_data.data)

    async def store(self, data: bytes, *, key: str, content_type: str | None = None) -> str:
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
    async def public_url(self, uri: str) -> str | None:
        """Return human-readable link for this URI.

        Args:
            uri: Full URI including PIPELEX_STORAGE_SCHEME prefix.

        Returns:
            Human-readable link for debugging/display.
        """
