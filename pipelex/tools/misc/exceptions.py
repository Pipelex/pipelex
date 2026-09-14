from typing import Self

import tomli

from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.system.exceptions import ToolError


class ArgumentTypeError(ToolError):
    pass


class JsonTypeError(ToolError):
    pass


class FileTypeError(ToolError):
    pass


class ContextProviderError(ToolError):
    def __init__(self, message: str, variable_name: str):
        super().__init__(message=message)
        self.variable_name = variable_name


class TomlError(ToolError):
    _declared_title = "TOML parse error"

    def __init__(self, message: str, doc: str, pos: int, lineno: int, colno: int):
        super().__init__(message)
        self.doc = doc
        self.pos = pos
        self.lineno = lineno
        self.colno = colno

    @classmethod
    def from_tomli_error(cls, exc: tomli.TOMLDecodeError) -> Self:
        return cls(message=exc.msg, doc=exc.doc, pos=exc.pos, lineno=exc.lineno, colno=exc.colno)


class RemoteFileFetchError(ToolError):
    """A remote file an input or a pipe referenced could not be fetched.

    Raised where the fetch happens — inside the operator that consumes the resource, the
    one honest test that a URL serves what it claims to. The URL is caller-supplied, so
    ``error_domain = INPUT`` and the message is caller-facing: it names the URL and what
    the server or the network said (an HTTP status, a refused connection, a timeout), and
    never a resolved address.
    """

    error_domain = ErrorDomain.INPUT
    _declared_title = "Remote file could not be fetched"
    _authors_caller_facing_message = True
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Check that the URL serves the file to a plain HTTP client, or upload the file and reference it instead.",
    )
