"""Where the package raises its errors and chooses their codes, read from the source without importing it.

The error-code gate (``tests/unit/pipelex/errors/test_error_code_gate.py``) needs two facts no import can give:
which class each ``raise`` statement constructs, so that an abstract base is never raised directly, and which
code each raise site chooses with ``with_error_code``, so that it is one its class declares. Both are read here
from the syntax tree of every module, which is pure and needs no Pipelex bootstrap.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from pathlib import Path

_CODE_ENUM_NAMES = frozenset({"CoreCode", "PipelexErrorCode"})


class RaisedClassSite(NamedTuple):
    """A ``raise`` statement that constructs a class by its name."""

    path: Path
    line: int
    class_name: str


class ChosenCodeSite(NamedTuple):
    """A ``with_error_code`` call on a class constructed in place, choosing a code by its enum member."""

    path: Path
    line: int
    class_name: str
    enum_name: str
    member_name: str


def constructed_class_name(node: ast.expr) -> str | None:
    """The name of the class an expression constructs, through any chain of methods called on the new instance.

    ``SomeError(msg)``, ``module.SomeError(msg)`` and ``SomeError(msg).with_error_code(code).with_params(name=value)``
    all construct ``SomeError``; a bare name, such as a re-raised variable, constructs nothing.
    """
    current: ast.expr = node
    while isinstance(current, ast.Call):
        func = current.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Call):
            current = func.value
            continue
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None
    return None


def _chosen_code(call: ast.Call) -> tuple[str, str] | None:
    if len(call.args) != 1 or call.keywords:
        return None
    argument = call.args[0]
    if isinstance(argument, ast.Attribute) and isinstance(argument.value, ast.Name) and argument.value.id in _CODE_ENUM_NAMES:
        return argument.value.id, argument.attr
    return None


def iter_raised_class_sites(*, path: Path, source: str) -> list[RaisedClassSite]:
    """Every ``raise`` in a module that constructs a class, with the class's name."""
    sites: list[RaisedClassSite] = []
    for node in ast.walk(ast.parse(source, filename=str(path))):
        if isinstance(node, ast.Raise) and node.exc is not None:
            class_name = constructed_class_name(node.exc)
            if class_name is not None:
                sites.append(RaisedClassSite(path=path, line=node.lineno, class_name=class_name))
    return sites


def iter_chosen_code_sites(*, path: Path, source: str) -> list[ChosenCodeSite]:
    """Every ``with_error_code(Enum.MEMBER)`` call on a class constructed in place, anywhere in a module."""
    sites: list[ChosenCodeSite] = []
    for node in ast.walk(ast.parse(source, filename=str(path))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "with_error_code" and isinstance(func.value, ast.Call)):
            continue
        class_name = constructed_class_name(func.value)
        chosen = _chosen_code(node)
        if class_name is None or chosen is None:
            continue
        enum_name, member_name = chosen
        sites.append(ChosenCodeSite(path=path, line=node.lineno, class_name=class_name, enum_name=enum_name, member_name=member_name))
    return sites
