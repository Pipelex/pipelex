from pipelex.system.exceptions import ToolError


class StorageError(ToolError):
    """Base exception for storage-related errors."""


class StorageFileNotFoundError(StorageError):
    """Raised when a requested file does not exist in storage."""


class StorageInvalidUriError(StorageError):
    """Raised when a URI is invalid (e.g., path traversal attempt or absolute path)."""
