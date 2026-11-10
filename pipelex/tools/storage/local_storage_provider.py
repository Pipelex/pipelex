import contextlib
import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, cast
from uuid import uuid4

import aiofiles
from typing_extensions import override

from pipelex.tools.misc.exceptions import FileTypeError
from pipelex.tools.misc.filetype_utils import detect_file_type_from_path
from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidUriError, StorageLocalError
from pipelex.tools.storage.storage_provider_abstract import StorageKind, StorageProviderAbstract, StoredData

# The name of the file holding a stored file's metadata, beside it: hidden, as the temporary files of a write are, and
# never a key a caller can name, so no read or write reaches it as a stored file of its own.
_SIDECAR_PREFIX = "."
_SIDECAR_SUFFIX = ".metadata.json"


def _sidecar_path_of(*, file_path: Path) -> Path:
    return file_path.with_name(f"{_SIDECAR_PREFIX}{file_path.name}{_SIDECAR_SUFFIX}")


def _is_sidecar_name(*, name: str) -> bool:
    return name.startswith(_SIDECAR_PREFIX) and name.endswith(_SIDECAR_SUFFIX)


def _sidecar_bytes_of(*, metadata: Mapping[str, str] | None) -> bytes:
    """The sidecar's content: the metadata as a JSON object, keys lowercase as they are read back."""
    lowercase_metadata = {meta_key.lower(): meta_value for meta_key, meta_value in (metadata or {}).items()}
    return json.dumps(lowercase_metadata, sort_keys=True).encode("utf-8")


# Held while a write publishes a file and its sidecar, which are two renames: two writers of one key in this process,
# on one event loop or on several threads, take turns, and neither publishes its bytes beside the other's metadata. The
# renames are all it guards, never an await, so it is held for microseconds and is one for every key.
_PUBLISH_LOCK = threading.Lock()


class LocalStorageProvider(StorageProviderAbstract):
    """Storage provider implementation for local filesystem storage.

    Files are stored relative to a root path, with keys being relative path strings. A file stored with metadata has
    it in a hidden JSON file beside it, `.<name>.metadata.json`, a name no key may take; a file stored again with no
    metadata loses its sidecar.

    A file and its sidecar are published as a pair: the metadata read beside a file is the metadata it was stored with,
    or none while a write is publishing them, never another write's. Writes of one key in this process take turns; a
    write that cannot publish the sidecar removes the file it published and fails, so a key never keeps bytes without
    the metadata they were stored with. Writers in separate processes are not ordered: this provider is for one
    machine's runs, and of two processes storing one key at once, the file may keep one's bytes and the other's
    metadata.
    """

    storage_kind: ClassVar[StorageKind] = "local"

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
            StorageInvalidUriError: If the key is invalid (a NUL byte, an absolute path or path traversal).
        """
        relative_path = Path(key)

        if relative_path.is_absolute():
            msg = f"Invalid key '{key}': absolute paths are not allowed"
            raise StorageInvalidUriError(msg)

        # A NUL byte cannot name a file, and resolve() rejects it with a bare ValueError
        if "\x00" in key:
            msg = f"Invalid key {key!r}: a null byte is not allowed"
            raise StorageInvalidUriError(msg)

        # The sidecar of a file's metadata is not a stored file: a key naming one would read or overwrite another's metadata.
        if _is_sidecar_name(name=relative_path.name):
            msg = f"Invalid key '{key}': the name is reserved for a stored file's metadata"
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
            StorageLocalError: If the filesystem read fails (e.g. permission denied, I/O error).
        """
        file_path = self._validate_key(key)

        if not file_path.exists():
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind)

        try:
            async with aiofiles.open(file_path, "rb") as file_handle:  # pyright: ignore[reportUnknownMemberType]
                data = await file_handle.read()
        except FileNotFoundError as exc:
            # TOCTOU: the file passed exists() above but was removed before the open.
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind) from exc
        except OSError as exc:
            msg = f"Failed to read file '{key}': {exc}"
            raise StorageLocalError(msg) from exc

        # Detect MIME type from file path
        mime_type: str | None = None
        try:
            file_type = detect_file_type_from_path(file_path)
            mime_type = file_type.mime
        except FileTypeError:
            pass  # MIME type detection failed, return None

        return StoredData(data=data, mime_type=mime_type)

    @override
    async def _load_head(self, key: str, *, nb_bytes: int) -> bytes:
        """Read the first bytes of a file, instead of the whole file.

        Args:
            key: Storage key (relative path, without scheme prefix).
            nb_bytes: How many leading bytes to read. A file shorter than this is read whole.

        Returns:
            At most `nb_bytes` leading bytes of the file.

        Raises:
            StorageFileNotFoundError: If the file does not exist.
            StorageInvalidUriError: If the key is invalid.
            StorageLocalError: If the filesystem read fails (e.g. permission denied, I/O error).
        """
        file_path = self._validate_key(key)
        try:
            async with aiofiles.open(file_path, "rb") as file_handle:  # pyright: ignore[reportUnknownMemberType]
                data: bytes = await file_handle.read(nb_bytes)
        except FileNotFoundError as exc:
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind) from exc
        except OSError as exc:
            msg = f"Failed to read file '{key}': {exc}"
            raise StorageLocalError(msg) from exc
        return data

    @override
    async def _load_size(self, key: str) -> int:
        """The size of a file, read from its metadata without opening it.

        Raises:
            StorageFileNotFoundError: If the file does not exist.
            StorageInvalidUriError: If the key is invalid.
            StorageLocalError: If the key names something that is not a file, or the filesystem cannot stat it.
        """
        file_path = self._validate_key(key)
        try:
            stat_result = file_path.stat()
        except FileNotFoundError as exc:
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg).with_params(scheme=self.storage_kind) from exc
        except OSError as exc:
            msg = f"Failed to read the size of file '{key}': {exc}"
            raise StorageLocalError(msg) from exc
        if not file_path.is_file():
            msg = f"Failed to read the size of '{key}': it is not a file"
            raise StorageLocalError(msg)
        return stat_result.st_size

    @staticmethod
    def _temporary_path_beside(*, file_path: Path) -> Path:
        return file_path.with_name(f".{file_path.name}.{uuid4().hex}.tmp")

    @staticmethod
    async def _write_temporary(*, temporary_path: Path, data: bytes) -> None:
        """Write the bytes to a temporary file beside their target, creating its folders, and flush them to disk.

        Raises:
            OSError: If the filesystem write fails.
        """
        temporary_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(temporary_path, "wb") as file_handle:  # pyright: ignore[reportUnknownMemberType]
            await file_handle.write(data)
            await file_handle.flush()
            os.fsync(file_handle.fileno())

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> None:
        """Store bytes to a file, published whole or not at all, with no metadata.

        Raises:
            StorageInvalidUriError: If the key is invalid.
            StorageLocalError: If the filesystem write fails (e.g. disk full, permission denied).
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
        """Store bytes to a file, published whole or not at all, and its metadata in the sidecar beside it.

        The bytes, and the sidecar when there is metadata, are written to temporary files beside their targets and
        flushed to disk first, so a full disk fails the write before anything is published. Then, holding the publishing
        lock: the old sidecar is removed, the bytes are renamed onto the file, which is atomic within one filesystem, and
        the new sidecar is renamed beside it. A reader never sees a file cut short, and sees the new bytes with no
        metadata for the moment between the two renames, never with the old file's. When the sidecar cannot be
        published, the file is removed and the write fails, rather than leaving bytes stored without their metadata.

        Args:
            data: The bytes to store.
            key: Storage key (relative path, without scheme prefix).
            content_type: Ignored for local storage.
            checksum_sha256_hex: Ignored: a file has no checksum of its own to send it to.
            metadata: String pairs to keep beside the file, or None for none.

        Raises:
            StorageInvalidUriError: If the key is invalid.
            StorageLocalError: If the filesystem write fails (e.g. disk full, permission denied).
        """
        file_path = self._validate_key(key)
        sidecar_path = _sidecar_path_of(file_path=file_path)
        temporary_path = self._temporary_path_beside(file_path=file_path)
        temporary_sidecar_path = self._temporary_path_beside(file_path=sidecar_path) if metadata else None

        try:
            await self._write_temporary(temporary_path=temporary_path, data=data)
            if temporary_sidecar_path is not None:
                await self._write_temporary(temporary_path=temporary_sidecar_path, data=_sidecar_bytes_of(metadata=metadata))
            with _PUBLISH_LOCK:
                sidecar_path.unlink(missing_ok=True)
                temporary_path.replace(file_path)
                if temporary_sidecar_path is not None:
                    self._publish_sidecar_or_withdraw(temporary_sidecar_path=temporary_sidecar_path, sidecar_path=sidecar_path, file_path=file_path)
        except OSError as exc:
            msg = f"Failed to write file '{key}': {exc}"
            raise StorageLocalError(msg) from exc
        finally:
            # Gone once renamed; a write that failed leaves them behind, and removing them is best effort.
            for leftover_path in (temporary_path, temporary_sidecar_path):
                if leftover_path is not None:
                    with contextlib.suppress(OSError):
                        leftover_path.unlink(missing_ok=True)

    @override
    async def _store_if_absent(self, *, data: bytes, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> bool:
        """Create a file unless one exists at the key, published whole or not at all, with no metadata.

        Returns:
            True when this call created the file, False when the key already held one.

        Raises:
            StorageInvalidUriError: If the key is invalid.
            StorageLocalError: If the filesystem write fails.
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
        """Create a file unless one exists at the key, published whole or not at all, and never over another.

        The bytes, and the sidecar when there is metadata, are written to temporary files beside their targets and
        flushed to disk, as `_store` writes them. Then, holding the publishing lock, the bytes are hard-linked to the target,
        which the filesystem creates only when the name is free, atomically: of two writers of one key, exactly one
        creates it, and neither replaces a file already there. A reader never sees a file cut short. Only the call that
        created the file publishes its sidecar, replacing or removing any left by a file removed without it, so a file
        already there keeps its own metadata. When the sidecar cannot be published, the file this call created is
        removed and the call fails, so the key is free for the next attempt rather than held forever by bytes without
        their metadata. A reader between the link and the sidecar's rename sees the new file with no metadata, or with a
        stale sidecar's, for that moment. The temporary files are removed either way.

        Args:
            data: The bytes to store, already checked against their checksum.
            key: Storage key (relative path, without scheme prefix).
            content_type: Ignored for local storage.
            checksum_sha256_hex: Checked before this call; a file has no checksum of its own to send it to.
            metadata: String pairs to keep beside the file this call creates, or None for none.

        Returns:
            True when this call created the file, False when the key already held one.

        Raises:
            StorageInvalidUriError: If the key is invalid.
            StorageLocalError: If the filesystem write fails, including on a filesystem that cannot make a hard link, or
                when the key names something that is not a file, or a path through a file.
        """
        file_path = self._validate_key(key)
        sidecar_path = _sidecar_path_of(file_path=file_path)
        temporary_path = self._temporary_path_beside(file_path=file_path)
        temporary_sidecar_path = self._temporary_path_beside(file_path=sidecar_path) if metadata else None

        created: bool
        try:
            await self._write_temporary(temporary_path=temporary_path, data=data)
            if temporary_sidecar_path is not None:
                await self._write_temporary(temporary_path=temporary_sidecar_path, data=_sidecar_bytes_of(metadata=metadata))
            with _PUBLISH_LOCK:
                # Only the link reads an existing name as the key held: the same error while preparing the temporary
                # file, from a file standing where a folder of the key should be, is a failure like any other.
                try:
                    file_path.hardlink_to(temporary_path)
                except FileExistsError:
                    created = False
                else:
                    created = True
                if not created and not file_path.is_file():
                    msg = f"Failed to create file '{key}': something that is not a file is there"
                    raise StorageLocalError(msg)
                if created:
                    if temporary_sidecar_path is None:
                        # A sidecar left by a file removed without it would otherwise be read as this file's.
                        self._remove_sidecar_or_withdraw(sidecar_path=sidecar_path, file_path=file_path)
                    else:
                        self._publish_sidecar_or_withdraw(
                            temporary_sidecar_path=temporary_sidecar_path, sidecar_path=sidecar_path, file_path=file_path
                        )
        except OSError as exc:
            msg = f"Failed to create file '{key}': {exc}"
            raise StorageLocalError(msg) from exc
        finally:
            # The target is its own link once created, and a write that failed leaves the temporary files behind:
            # removing them is best effort.
            for leftover_path in (temporary_path, temporary_sidecar_path):
                if leftover_path is not None:
                    with contextlib.suppress(OSError):
                        leftover_path.unlink(missing_ok=True)
        return created

    @staticmethod
    def _publish_sidecar_or_withdraw(*, temporary_sidecar_path: Path, sidecar_path: Path, file_path: Path) -> None:
        """Rename the written sidecar beside the file just published, or remove that file when it cannot be.

        Raises:
            OSError: If the rename fails, once the file is removed.
        """
        try:
            temporary_sidecar_path.replace(sidecar_path)
        except OSError:
            with contextlib.suppress(OSError):
                file_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _remove_sidecar_or_withdraw(*, sidecar_path: Path, file_path: Path) -> None:
        """Remove a stale sidecar beside the file just created, or remove that file when it cannot be.

        Raises:
            OSError: If the removal fails, once the file is removed.
        """
        try:
            sidecar_path.unlink(missing_ok=True)
        except OSError:
            with contextlib.suppress(OSError):
                file_path.unlink(missing_ok=True)
            raise

    @override
    async def _load_metadata(self, key: str) -> Mapping[str, str]:
        """The metadata kept in the sidecar beside a file, empty when it was stored with none.

        Raises:
            StorageFileNotFoundError: If the file does not exist.
            StorageInvalidUriError: If the key is invalid.
            StorageLocalError: If the key names something that is not a file, or the sidecar cannot be read.
        """
        await self._load_size(key)
        sidecar_path = _sidecar_path_of(file_path=self._validate_key(key))
        try:
            sidecar_text = sidecar_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as exc:
            msg = f"Failed to read the metadata of file '{key}': {exc}"
            raise StorageLocalError(msg) from exc
        try:
            parsed: Any = json.loads(sidecar_text)
        except json.JSONDecodeError as exc:
            msg = f"The metadata of file '{key}' is not valid JSON: {exc.msg}"
            raise StorageLocalError(msg) from exc
        if not isinstance(parsed, dict):
            msg = f"The metadata of file '{key}' is not a JSON object"
            raise StorageLocalError(msg)
        metadata: dict[str, str] = {}
        for meta_key, meta_value in cast("dict[Any, Any]", parsed).items():
            if not isinstance(meta_key, str) or not isinstance(meta_value, str):
                msg = f"The metadata of file '{key}' holds a value that is not a string"
                raise StorageLocalError(msg)
            metadata[meta_key.lower()] = meta_value
        return metadata

    @override
    async def public_url(self, uri: str) -> str:
        """Return a file:// URI for this storage URI.

        Args:
            uri: Full URI including pipelex-storage:// scheme.

        Returns:
            file:// URI that can be clicked in terminals like Cursor.
        """
        key = self._strip_scheme(uri)
        file_path = self._validate_key(key)
        return file_path.as_uri()
