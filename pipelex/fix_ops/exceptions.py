from pipelex.base_exceptions import PipelexError, PipelexUnexpectedError


class FixWriteConflictError(PipelexError):
    """A file changed after a fix or a migration read it but before the atomic commit."""


class FixTransactionError(PipelexUnexpectedError):
    """A multi-file commit failed and could not be fully rolled back."""
