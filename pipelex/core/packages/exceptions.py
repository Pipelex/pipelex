from pipelex.base_exceptions import PipelexError


class ManifestError(PipelexError):
    pass


class ManifestParseError(ManifestError):
    pass


class ManifestValidationError(ManifestError):
    pass


class VCSFetchError(PipelexError):
    """Raised when a git clone or tag listing operation fails."""


class VersionResolutionError(PipelexError):
    """Raised when no version satisfying the constraint can be found in remote tags."""


class PackageCacheError(PipelexError):
    """Raised when cache operations (lookup, store) fail."""


class LockFileError(PipelexError):
    """Raised when lock file parsing, generation, or I/O fails."""


class IntegrityError(PipelexError):
    """Raised when a cached package does not match its lock file hash."""
