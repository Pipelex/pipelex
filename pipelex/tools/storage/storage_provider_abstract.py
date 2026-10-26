import hashlib
from abc import ABC, abstractmethod
from typing import ClassVar, Literal, NamedTuple

from mthds.protocol.problem.registry import CoreCode

from pipelex.tools.storage.exceptions import StorageChecksumMismatchError, StorageFileNotFoundError, StorageInvalidKeyError

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
        - _store(data, key, content_type, checksum_sha256_hex): Store data
        - public_url(uri): Return human-readable link for URI

    A subclass holding a client open between operations overrides ``teardown`` to close it.

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

    async def store(self, data: bytes, *, key: str, content_type: str | None = None, checksum_sha256_hex: str | None = None) -> str:
        """Store data and return full URI with scheme.

        A provider whose storage can check a write's checksum, as S3 can, sends the bytes' SHA-256 with every write, so
        the storage refuses a body that arrived damaged and keeps the checksum beside the object. A caller that hashed
        the bytes already, for their key, passes the digest, so they are not hashed again. Unlike `store_if_absent`,
        which checks a checksum handed to it, this trusts the caller's, which is the hash of bytes the caller holds, and
        S3 still refuses a body that does not match it.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the data (used by cloud providers).
            checksum_sha256_hex: The SHA-256 of `data` in lowercase hexadecimal, when the caller has it, or None.

        Returns:
            Full URI with PIPELEX_STORAGE_SCHEME prefix.
        """
        uri = self._add_scheme(key)
        await self._store(data=data, key=key, content_type=content_type, checksum_sha256_hex=checksum_sha256_hex)
        return uri

    @abstractmethod
    async def _store(self, data: bytes, *, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> None:
        """Store data in storage.

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the data.
            checksum_sha256_hex: The SHA-256 of `data` in lowercase hexadecimal, or None when the caller has not hashed
                the bytes. A provider whose storage checks a write's checksum sends it, hashing the bytes itself when it
                is None; another ignores it.
        """

    async def store_if_absent(
        self,
        *,
        data: bytes,
        key: str,
        content_type: str | None = None,
        checksum_sha256_hex: str | None = None,
    ) -> bool:
        """Create the object at `key` unless one exists there, and say whether this call created it.

        A create-only write never replaces an object: when the key already holds one, nothing is written and the
        answer is False, whatever the object holds. With `checksum_sha256_hex`, the bytes are checked against it
        before anything is sent, and a provider whose storage can check a write's checksum itself sends it too, so
        the object holds exactly the bytes the checksum names (S3 checks `x-amz-checksum-sha256` against the body it
        receives).

        Args:
            data: The bytes to store.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the data (used by cloud providers).
            checksum_sha256_hex: The SHA-256 of `data` in lowercase hexadecimal, or None to send no checksum.

        Returns:
            True when this call created the object, False when the key already held one.

        Raises:
            StorageInvalidKeyError: If the key includes the scheme prefix.
            StorageChecksumMismatchError: If `data` does not hash to `checksum_sha256_hex`.
        """
        self._add_scheme(key)
        if checksum_sha256_hex is not None and hashlib.sha256(data).hexdigest() != checksum_sha256_hex:
            msg = f"The bytes to store under '{key}' do not hash to the checksum {checksum_sha256_hex!r} given with them: nothing was stored."
            raise StorageChecksumMismatchError(msg)
        return await self._store_if_absent(data=data, key=key, content_type=content_type, checksum_sha256_hex=checksum_sha256_hex)

    async def _store_if_absent(self, *, data: bytes, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> bool:
        """Create the object at `key` unless one exists there, by key.

        This default looks the key up, then stores the bytes when it holds nothing, so a provider that cannot make a
        write conditional, an external storage plugin included, keeps working. Two writers racing on one free key may
        then both store, the last one winning, which a caller keying objects by their content, as a blob store does,
        can live with, since both write the same bytes. A provider that can create an object only when its key is
        free overrides it, and a storage that refuses unconditional writes needs that override.

        Args:
            data: The bytes to store, already checked against `checksum_sha256_hex`.
            key: Storage key (without scheme prefix).
            content_type: Optional MIME type for the data.
            checksum_sha256_hex: The SHA-256 of `data`, or None, handed on to `_store`.

        Returns:
            True when this call stored the object, False when the key already held one.
        """
        try:
            await self._load_size(key)
        except StorageFileNotFoundError:
            await self._store(data=data, key=key, content_type=content_type, checksum_sha256_hex=checksum_sha256_hex)
            return True
        return False

    def teardown(self) -> None:
        """Release what the provider keeps open between operations, such as a client and its connections.

        The runtime's teardown calls it on the provider it booted with, from synchronous code, possibly on the thread
        running the event loop the provider served. This default holds nothing. A provider that keeps a client
        bound to an event loop closes it on that loop, scheduling the close on a loop still running rather than
        waiting for it, and must still work afterwards, opening a new client on its next operation.
        """

    @abstractmethod
    async def public_url(self, uri: str) -> str | None:
        """Return human-readable link for this URI.

        Args:
            uri: Full URI including PIPELEX_STORAGE_SCHEME prefix.

        Returns:
            Human-readable link for debugging/display.
        """
