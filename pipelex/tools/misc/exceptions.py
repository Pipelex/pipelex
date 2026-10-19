from typing import Any, ClassVar, Self

import tomli
from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, ErrorCodeSet
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.system.exceptions import ToolError


class ArgumentTypeError(ToolError):
    """Raised when a helper is handed a value of a type it does not take, which is a bug of its caller."""

    error_code = CoreCode.RUNTIME_UNEXPECTED


class JsonTypeError(ToolError):
    """Raised when a JSON document parses but its top level is not the type its reader expects.

    One helper serves several readers: a CLI inputs file is ``request.invalid`` (the default), a credentials
    file the configuration names is ``pipelex.config.invalid``, and a document the runtime wrote itself is
    ``runtime.unexpected``.
    """

    error_code = ErrorCodeSet(default=CoreCode.REQUEST_INVALID, others=(PipelexErrorCode.CONFIG_INVALID, CoreCode.RUNTIME_UNEXPECTED))


class FileTypeError(ToolError):
    """Raised when the type of a file cannot be identified from its bytes.

    An input file is ``input.file_type_unsupported`` (the default); bytes a provider returned are
    ``provider.response_invalid``, which the provider's raise site chooses.
    """

    error_code = ErrorCodeSet(default=CoreCode.INPUT_FILE_TYPE_UNSUPPORTED, others=(CoreCode.PROVIDER_RESPONSE_INVALID,))


class ContextProviderError(ToolError):
    """Base of the errors a context provider raises when it cannot give a variable's value."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR

    def __init__(self, message: str, variable_name: str):
        super().__init__(message=message)
        self.variable_name = variable_name


class TomlError(ToolError):
    """Raised when a TOML document does not parse.

    Most TOML the runtime reads is its own configuration, so the default is ``pipelex.config.syntax``. A raise
    or catch site that reads a caller's request file chooses ``request.malformed``, and one that reads a
    method's file chooses ``method.syntax``.
    """

    error_code = ErrorCodeSet(default=PipelexErrorCode.CONFIG_SYNTAX, others=(CoreCode.REQUEST_MALFORMED, CoreCode.METHOD_SYNTAX))

    def __init__(self, message: str, doc: str, pos: int, lineno: int, colno: int):
        super().__init__(message)
        self.doc = doc
        self.pos = pos
        self.lineno = lineno
        self.colno = colno

    @override
    def problem_params(self) -> dict[str, Any]:
        # The parser's own words, which name a position in the document and never its text.
        return {"reason": self.message, "finding": self.message, "line": self.lineno, "column": self.colno}

    @classmethod
    def from_tomli_error(cls, exc: tomli.TOMLDecodeError) -> Self:
        return cls(message=exc.msg, doc=exc.doc, pos=exc.pos, lineno=exc.lineno, colno=exc.colno)


class RemoteFileFetchError(ToolError):
    """A remote file an input or a pipe referenced could not be fetched.

    Raised where the fetch happens — inside the operator that consumes the resource, the
    one honest test that a URL serves what it claims to. The message names the URL and what
    the server or the network said (an HTTP status, a refused connection, a timeout), and never
    a resolved address; it reaches the operator's diagnostics, the caller reading the sentence
    its code renders.

    A server that answered but would not serve the file is ``input.file_unreadable`` (the
    default); a timeout or a refused connection, which a retry may get past, is
    ``input.url_unreachable``; a file a provider's answer pointed at is
    ``provider.response_invalid``, which the provider's raise site chooses.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.INPUT_FILE_UNREADABLE,
        others=(CoreCode.INPUT_URL_UNREACHABLE, CoreCode.PROVIDER_RESPONSE_INVALID),
    )
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Check that the URL serves the file to a plain HTTP client, or upload the file and reference it instead.",
    )


class SemVerError(ToolError):
    """Raised when a version or a version constraint a method package declares does not parse."""

    error_code = CoreCode.METHOD_PACKAGE_INVALID


class UrlSyntaxError(ToolError, ValueError):
    """Raised when a URL is not a well-formed http(s) URL, checked without touching the network.

    Also a ``ValueError``, which the input checks that call it catch to name the input.
    """

    error_code = CoreCode.INPUT_INVALID


class LocalFileMissingError(ToolError, ValueError):
    """Raised when a local path a value points at names no file.

    Also a ``ValueError``, which the pipe's input check that calls it catches to name the input.
    """

    error_code = CoreCode.INPUT_REFERENCE_NOT_FOUND


class UnsupportedImageMimeTypeError(ToolError, ValueError):
    """Raised when a MIME type is not one of the image formats Pipelex reads and writes.

    An input's image is ``input.file_type_unsupported`` (the default); an image a provider returned is
    ``provider.response_invalid``, which the provider's raise site chooses. Also a ``ValueError``, since the
    check also runs inside a pydantic validator.
    """

    error_code = ErrorCodeSet(default=CoreCode.INPUT_FILE_TYPE_UNSUPPORTED, others=(CoreCode.PROVIDER_RESPONSE_INVALID,))
