import contextlib
import json
import os
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


class LocalStorageProvider(StorageProviderAbstract):
    """Storage provider implementation for local filesystem storage.

    Files are stored relative to a root path, with keys being relative path strings. A file stored with metadata has
    it in a hidden JSON file beside it, `.<name>.metadata.json`, a name no key may take; a file stored again with no
    metadata loses its sidecar, so the metadata read back is always the last write's.
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

        The bytes are written to a temporary file beside the target, flushed to disk, then renamed onto the target,
        which is atomic within one filesystem: a reader, or a process checking whether the key exists, never sees a
        file a full disk or a killed process cut short. Two writers of one key each write their own temporary file,
        and the last rename wins whole. The sidecar is then written the same way, or removed when there is no metadata,
        so a file stored again never keeps the metadata of the one it replaced.

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
        temporary_path = self._temporary_path_beside(file_path=file_path)

        try:
            await self._write_temporary(temporary_path=temporary_path, data=data)
            temporary_path.replace(file_path)
            await self._publish_sidecar(file_path=file_path, metadata=metadata)
        except OSError as exc:
            msg = f"Failed to write file '{key}': {exc}"
            raise StorageLocalError(msg) from exc
        finally:
            # Gone once renamed; a write that failed leaves it behind, and removing it is best effort.
            with contextlib.suppress(OSError):
                temporary_path.unlink(missing_ok=True)

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

        The bytes are written to a temporary file beside the target and flushed to disk, as `_store` writes them, then
        hard-linked to the target, which the filesystem creates only when the name is free, atomically: of two writers
        of one key, exactly one creates it, and neither replaces a file already there. A reader never sees a file cut
        short. The temporary file is removed either way. Only the call that created the file writes its sidecar, so a
        file already there keeps its own metadata; a reader between the link and the sidecar's rename sees the new
        file with no metadata for that moment.

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
        temporary_path = self._temporary_path_beside(file_path=file_path)

        created: bool
        try:
            await self._write_temporary(temporary_path=temporary_path, data=data)
            # Only the link reads an existing name as the key held: the same error while preparing the temporary file,
            # from a file standing where a folder of the key should be, is a failure like any other.
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
                # A sidecar left by a file removed without it would otherwise be read as this file's.
                await self._publish_sidecar(file_path=file_path, metadata=metadata)
        except OSError as exc:
            msg = f"Failed to create file '{key}': {exc}"
            raise StorageLocalError(msg) from exc
        finally:
            # The target is its own link once created, and a write that failed leaves the temporary file behind:
            # removing it is best effort.
            with contextlib.suppress(OSError):
                temporary_path.unlink(missing_ok=True)
        return created

    async def _publish_sidecar(self, *, file_path: Path, metadata: Mapping[str, str] | None) -> None:
        """Write the metadata of the file at `file_path` to its sidecar whole, or remove the sidecar when there is none.

        Raises:
            OSError: If the filesystem write fails.
        """
        sidecar_path = _sidecar_path_of(file_path=file_path)
        if not metadata:
            sidecar_path.unlink(missing_ok=True)
            return
        lowercase_metadata = {meta_key.lower(): meta_value for meta_key, meta_value in metadata.items()}
        sidecar_bytes = json.dumps(lowercase_metadata, sort_keys=True).encode("utf-8")
        temporary_path = self._temporary_path_beside(file_path=sidecar_path)
        try:
            await self._write_temporary(temporary_path=temporary_path, data=sidecar_bytes)
            temporary_path.replace(sidecar_path)
        finally:
            with contextlib.suppress(OSError):
                temporary_path.unlink(missing_ok=True)

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
