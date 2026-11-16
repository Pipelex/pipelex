from enum import StrEnum
from typing import Any

from mthds.protocol.problem.models import ProblemLocation
from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import SecurityError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.errors.error_code_declaration import ErrorCodeSet
from pipelex.errors.problem import make_location
from pipelex.errors.security_target import SecurityTargetClass
from pipelex.system.exceptions import ToolError


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

    def __init__(self, message: str, *, reason: UriReadRefusalReason, input_name: str | None = None, field: str | None = None):
        super().__init__(message)
        self.reason = reason
        # The run input whose file the URL is, when the caller gave it: the `input` of `security.input_url_refused`, the
        # root of the file's path. The path down to the file, the input included, such as `documents[1]`, is the
        # location's `field`.
        self.input_name = input_name
        self.field = field
        # The reason is the class of destination refused, so the security event names it without the raise site saying so.
        self.with_security_target_class(reason.target_class)

    @override
    def problem_params(self) -> dict[str, Any]:
        # The problem's `target_class` is a value the registry lists, which the code's sentence reads as a word ("points
        # at a private target"): `scheme` for a local path, and `private` for another tenant's key, which the registry
        # lists no value for. The security event names the finer class the refusal states, `foreign_storage_key`.
        params: dict[str, Any] = {"reason": self.reason.desc, "target_class": self.reason.target_class.listed_target_class}
        if self.input_name is not None:
            params["input"] = self.input_name
        return params

    @override
    def problem_location(self) -> ProblemLocation | None:
        return make_location(input_name=self.input_name, field=self.field)


# The kind of file a stored value is read as, the `file_type` of `input.file_unreadable`.
STORED_TEXT_FILE_TYPE = "text"


class StoredTextUnreadableReason(StrEnum):
    """Why the text behind a stored value's URL could not be read as one, the `reason` of `input.file_unreadable`."""

    # The bytes do not decode as UTF-8, the encoding every stored text is written in.
    NOT_UTF8 = "not_utf8"
    # The stored text is not valid JSON, for a JSON value.
    INVALID_JSON = "invalid_json"
    # The stored JSON is valid but is not an object, which a JSON value holds.
    NOT_A_JSON_OBJECT = "not_a_json_object"
    # The stored value declares a MIME type that is not of its kind, such as a JSON value declared `text/plain`.
    MIME_TYPE_MISMATCH = "mime_type_mismatch"


class UriTextNotUtf8Error(ToolError):
    """Raised when the bytes behind a URL read as a text are not UTF-8.

    A stored text, HTML or JSON value is written as UTF-8 by the code that stores it, so bytes that do not decode are a
    URL a caller or a method pointed at a file that is not a text, or, far more rarely, a stored object damaged since.
    It is the caller's to fix, so it is ``input.file_unreadable``, naming the input whose value it is when the reader
    knows it. The message names where the URL sat, never the URL itself, which can be a signed link holding a credential.
    """

    error_code = CoreCode.INPUT_FILE_UNREADABLE

    def __init__(self, message: str, *, input_name: str | None = None):
        super().__init__(message)
        self.input_name = input_name

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"input": self.input_name, "file_type": STORED_TEXT_FILE_TYPE, "reason": StoredTextUnreadableReason.NOT_UTF8}

    @override
    def problem_location(self) -> ProblemLocation | None:
        return make_location(input_name=self.input_name, field=None)


class UriTextTooLargeError(ToolError):
    """Raised when the text behind a URL is larger than a text the runtime reads.

    A stored value is read whole, so it is bounded by `[runtime.network] max_fetch_bytes`, the most bytes any read of a
    URL takes, whatever kind of URL it is: a stored object is sized before it is read, a data URL by the length of its
    text, and an http(s) URL's body as the fetch streams it, which raises the fetch's own `RemoteFileTooLargeError`. The
    URL is the caller's or a method's, so it is ``input.too_large``, naming the input whose value it is when known.
    """

    error_code = CoreCode.INPUT_TOO_LARGE
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Use a smaller text, or raise [runtime.network] max_fetch_bytes if you run the runtime yourself.",
    )

    def __init__(self, message: str, *, limit: int, size: int, input_name: str | None = None):
        super().__init__(message)
        self.limit = limit
        self.size = size
        self.input_name = input_name

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"input": self.input_name, "limit": self.limit, "size": self.size}

    @override
    def problem_location(self) -> ProblemLocation | None:
        return make_location(input_name=self.input_name, field=None)
