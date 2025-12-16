from pathlib import Path

from typing_extensions import override

from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidUriError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


class LocalStorageProvider(StorageProviderAbstract):
    """Storage provider implementation for local filesystem storage.

    Files are stored relative to a root path, with URIs being relative path strings.
    """

    def __init__(self, root_path: Path) -> None:
        """Initialize the local storage provider.

        Args:
            root_path: The base directory for all storage operations.
        """
        self._root_path = root_path

    def _validate_uri(self, uri: str) -> Path:
        """Validate the URI and return the resolved absolute path.

        Args:
            uri: The relative path URI to validate.

        Returns:
            The resolved absolute path.

        Raises:
            StorageInvalidUriError: If the URI is invalid (absolute path or path traversal).
        """
        relative_path = Path(uri)

        if relative_path.is_absolute():
            msg = f"Invalid URI '{uri}': absolute paths are not allowed"
            raise StorageInvalidUriError(msg)

        resolved_path = (self._root_path / relative_path).resolve()

        # Check for path traversal attempts
        try:
            resolved_path.relative_to(self._root_path.resolve())
        except ValueError as exc:
            msg = f"Invalid URI '{uri}': path traversal is not allowed"
            raise StorageInvalidUriError(msg) from exc

        return resolved_path

    @override
    def load(self, uri: str) -> bytes:
        """Load bytes from a file at the given URI.

        Args:
            uri: The relative path to the file.

        Returns:
            The file contents as bytes.

        Raises:
            StorageFileNotFoundError: If the file does not exist.
            StorageInvalidUriError: If the URI is invalid.
        """
        file_path = self._validate_uri(uri)

        if not file_path.exists():
            msg = f"File not found: '{uri}'"
            raise StorageFileNotFoundError(msg)

        return file_path.read_bytes()

    @override
    def store(self, data: bytes, uri: str) -> str:
        """Store bytes to a file at the given URI.

        Args:
            data: The bytes to store.
            uri: The relative path where to store the file.

        Returns:
            The URI of the stored file.

        Raises:
            StorageInvalidUriError: If the URI is invalid.
        """
        file_path = self._validate_uri(uri)

        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_path.write_bytes(data)

        return uri
