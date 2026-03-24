from pipelex.libraries.exceptions import LibraryError


class LibraryCrateError(LibraryError):
    """Raised when building a LibraryCrate fails (e.g. ref collision)."""
