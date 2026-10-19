from enum import StrEnum
from typing import Any

from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import SecurityError
from pipelex.errors.error_code_declaration import ErrorCodeSet
from pipelex.errors.security_target import SecurityTargetClass


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

    @property
    def target_class(self) -> SecurityTargetClass:
        """The class of destination the refusal names in its security event: another tenant's key, or a scheme the run does not read."""
        match self:
            case UriReadRefusalReason.FOREIGN_STORAGE_KEY:
                return SecurityTargetClass.FOREIGN_STORAGE_KEY
            case UriReadRefusalReason.LOCAL_PATH:
                return SecurityTargetClass.SCHEME


class UriReadRefusedError(SecurityError):
    """Raised when a run asks to read a URL outside what its host lets it read.

    On a run whose host supplied a read scope, a ``pipelex-storage://`` key is read only when it
    lies under that scope, and a bare path or a ``file://`` URI is never read (see
    :mod:`pipelex.tools.uri.uri_read_scope`). A value can carry any URL its method chose — a
    construct that assembles one from plain text, a model's structured output, a function's
    result — so the refusal happens where the value is read, whichever pipe produced it.

    A :class:`SecurityError`, so that a domain-level ``except`` around a read cannot swallow it.
    The default is ``security.input_url_refused``, answered as a 422: an input asked for the read
    and the caller fixes it by passing the file as an input or an upload. A raise or catch site that
    knows the method named the URL chooses ``security.method_url_refused``. The message names
    where the URL sat (an image of a pipe's prompt, an input) and why it was refused, and quotes
    neither the URL nor the read scope. The refusal happens before any IO, so it says nothing about whether the file
    exists.
    """

    error_code = ErrorCodeSet(default=CoreCode.SECURITY_INPUT_URL_REFUSED, others=(CoreCode.SECURITY_METHOD_URL_REFUSED,))

    def __init__(self, message: str, *, reason: UriReadRefusalReason):
        super().__init__(message)
        self.reason = reason
        # The reason is the class of destination refused, so the security event names it without the raise site saying so.
        self.with_security_target_class(reason.target_class)

    @override
    def problem_params(self) -> dict[str, Any]:
        # The problem's `target_class` is a value the registry lists, which the code's sentence reads as a word ("points
        # at a private target"): `scheme` for a local path, and `private` for another tenant's key, which the registry
        # lists no value for. The security event names the finer class the refusal states, `foreign_storage_key`.
        return {"reason": self.reason.desc, "target_class": self.reason.target_class.listed_target_class}
