from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.system.exceptions import ToolError

if TYPE_CHECKING:
    import tomli


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
    def from_tomli_error(cls, exc: tomli.TOMLDecodeError) -> TomlError:
        return cls(message=exc.msg, doc=exc.doc, pos=exc.pos, lineno=exc.lineno, colno=exc.colno)
