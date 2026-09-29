from enum import StrEnum

from pipelex.base_exceptions import ErrorDomain, SecurityError


class UriReadRefusalReason(StrEnum):
    """Why a run was refused a read, as the caller can act on it."""

    FOREIGN_STORAGE_KEY = "foreign_storage_key"
    LOCAL_PATH = "local_path"

    @property
    def desc(self) -> str:
        match self:
            case UriReadRefusalReason.FOREIGN_STORAGE_KEY:
                return "it names a stored file this run may not read"
            case UriReadRefusalReason.LOCAL_PATH:
                return "it names a file on the server's own disk, or a URL in a scheme this runtime does not read, and a hosted run reads neither"


class UriReadRefusedError(SecurityError):
    """Raised when a run asks to read a URL outside what its host lets it read.

    On a run whose host supplied a read scope, a ``pipelex-storage://`` key is read only when it
    lies under that scope, and a bare path or a ``file://`` URI is never read (see
    :mod:`pipelex.tools.uri.uri_read_scope`). A value can carry any URL its method chose — a
    construct that assembles one from plain text, a model's structured output, a function's
    result — so the refusal happens where the value is read, whichever pipe produced it.

    A :class:`SecurityError`, so that a domain-level ``except`` around a read cannot swallow it.
    ``error_domain = INPUT``, answered as a 422, because the method or its inputs asked for the
    read and the caller fixes it by passing the file as an input or an upload. The message is
    caller-facing and keeps its text under STRICT disclosure: it names where the URL sat (an
    image of a pipe's prompt, an input) and why it was refused, and quotes neither the URL nor the
    read scope. The refusal happens before any IO, so it says nothing about whether the file
    exists.
    """

    error_domain = ErrorDomain.INPUT
    _declared_title = "Read outside the run's scope refused"
    _authors_caller_facing_message = True

    def __init__(self, message: str, *, reason: UriReadRefusalReason):
        super().__init__(message)
        self.reason = reason
