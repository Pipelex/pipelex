from pipelex.base_exceptions import PipelexConfigError
from pipelex.system.exceptions import ToolError


class StorageError(ToolError):
    """Base exception for storage-related errors."""


class StorageConfigError(StorageError, PipelexConfigError):
    """Raised when a storage configuration is invalid."""


class StorageFileNotFoundError(StorageError):
    """Raised when a requested file does not exist in storage."""


class StorageInvalidUriError(StorageError):
    """Raised when a URI is invalid (e.g., path traversal attempt or absolute path)."""


class StorageInvalidKeyError(StorageError):
    """Raised when a storage key is invalid (e.g., contains scheme prefix)."""


class StorageS3Error(StorageError):
    """Raised when an S3 storage operation fails."""


class StorageGcpError(StorageError):
    """Raised when a GCP storage operation fails."""


class StorageGcpCredentialsError(StorageGcpError):
    """Raised when GCP credentials file is not found or invalid."""
