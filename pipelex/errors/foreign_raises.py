"""The raises, in our own code, of exception classes outside the ``PipelexError`` root.

An error raised outside the root carries no registry code: whatever reader it reaches gets the catch-all
``runtime.unexpected``, or worse a raw library message. So a raise a reader can see constructs a coded class,
and the check this module feeds (``tests/unit/pipelex/errors/test_foreign_raises.py``) catches a new foreign
raise where one is practical, as ``wip/error-handling/census.md`` ("Raises outside the root") describes.

Some foreign raises are right, and the scan allows them by their shape:

- a builtin raised inside a pydantic validator or serializer, which pydantic wraps into its own error and which
  takes the code of the boundary that catches it;
- ``NotImplementedError`` inside an abstract method or a ``Protocol``;
- any raise inside a data-model dunder (``__getitem__``, ``__getattr__``, ``__iter__`` and the like), which is
  how Python and Jinja learn that a key, an attribute or an item is missing;
- the framework carriers a library expects by type (:data:`FRAMEWORK_CARRIER_NAMES`);
- developer, release and test code (:data:`EXEMPT_DIRECTORY_NAMES`).

The rest are listed with their disposition in ``tests/data/errors/foreign_raises.txt``: an invariant raised
only on a bug of ours, which a boundary reports as ``runtime.unexpected``; a builtin raised in a helper only
validators call; a private class caught in the module that defines it; a carrier the scan cannot recognise
by its name; developer tooling outside the exempt directories; or a builtin of a module that must import nothing
of Pipelex, which its every caller catches. The check fails on a foreign raise that file does not list, and on a
listed one that is gone. A class whose name starts with an underscore is read as a variable re-raised, so a
private sentinel is never listed.

Pure: the scan reads the syntax tree of every module and imports nothing.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, NamedTuple

from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

ROOT_ERROR_CLASS_NAME = "PipelexError"
"""The root every coded error joins."""

VALIDATOR_DECORATOR_NAMES: frozenset[str] = frozenset(
    {"field_validator", "model_validator", "validator", "root_validator", "field_serializer", "model_serializer"}
)
"""Pydantic's decorators, inside which a builtin raise is wrapped by pydantic into its own error."""

VALIDATOR_EXCEPTION_NAMES: frozenset[str] = frozenset({"ValueError", "TypeError", "AssertionError", "PydanticCustomError"})
"""The exceptions pydantic turns into a validation error when a validator raises them."""

DATA_MODEL_DUNDER_NAMES: frozenset[str] = frozenset(
    {
        "__getitem__",
        "__getattr__",
        "__getattribute__",
        "__setattr__",
        "__delattr__",
        "__iter__",
        "__next__",
        "__anext__",
        "__len__",
        "__contains__",
        "__missing__",
        "__html__",
        "__reduce__",
    }
)
"""The dunders whose raises are how Python's data model, and Jinja's, learn that something is missing."""

FRAMEWORK_CARRIER_NAMES: frozenset[str] = frozenset(
    {
        # The CLI framework's own exits and refusals, which it renders itself.
        "Exit",
        "Abort",
        "BadParameter",
        "UsageError",
        "SystemExit",
        "KeyboardInterrupt",
        # The iteration and generator protocols.
        "StopIteration",
        "StopAsyncIteration",
        "GeneratorExit",
        # Temporal's failure carrier, Jinja's template refusals inside the render budget and the sandbox,
        # httpcore's refused connection inside the SSRF guard's transport, google-auth's refresh refusal,
        # kajson's decoder refusal inside the payload decoder, and the print protocol's end of stream.
        "ApplicationError",
        "TemplateError",
        "JinjaSecurityError",
        "ConnectError",
        "RefreshError",
        "KajsonDecoderError",
        "EOFError",
    }
)
"""The carriers a library expects by type, kept as they are wherever they are raised."""

EXEMPT_DIRECTORY_NAMES: frozenset[str] = frozenset({"dev_cli", "test_extras", "test_helpers", "scripts", "migrations"})
"""Developer, release, migration and test code, which the check does not read."""


class ForeignRaiseSite(NamedTuple):
    """A raise of a class outside the root, by the module, the function and the class it raises."""

    path: str
    function: str
    exception: str
    line: int

    @property
    def key(self) -> tuple[str, str, str]:
        """The site without its line, which moves with every edit above it."""
        return (self.path, self.function, self.exception)


def collect_root_error_class_names(*, sources: Iterable[tuple[Path, str]]) -> frozenset[str]:
    """The names of every class, across the given sources, that derives from the root by its bases' names.

    Read from the syntax tree alone, so that the runner's classes, which the package cannot import, count too.

    Args:
        sources: Each module's path and source.

    Returns:
        The root's name and the name of every class whose bases reach it.
    """
    bases_by_name: dict[str, set[str]] = {}
    for path, source in sources:
        for node in ast.walk(ast.parse(source, filename=str(path))):
            if isinstance(node, ast.ClassDef):
                expression_names = {_expression_name(base) for base in node.bases}
                bases_by_name.setdefault(node.name, set()).update(name for name in expression_names if name is not None)
    rooted: set[str] = {ROOT_ERROR_CLASS_NAME}
    grew = True
    while grew:
        grew = False
        for name, base_names in bases_by_name.items():
            if name not in rooted and base_names & rooted:
                rooted.add(name)
                grew = True
    return frozenset(rooted)


def _expression_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _expression_name(node.value)
    return None


def _raised_class_name(node: ast.expr) -> str | None:
    """The class a raise constructs, through any chain of methods called on the new instance, or names bare."""
    current: ast.expr = node
    while isinstance(current, ast.Call):
        func = current.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Call):
            current = func.value
            continue
        current = func
        break
    name = _expression_name(current)
    if name is None or not name[:1].isupper():
        # A lowercase name is a variable holding an exception being re-raised, not a class.
        return None
    return name


def _decorator_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = _expression_name(target)
        if name is not None:
            names.add(name)
    return names


class _ForeignRaiseVisitor(ast.NodeVisitor):
    def __init__(self, *, path: str, root_names: frozenset[str]) -> None:
        self.path = path
        self.root_names = root_names
        self.sites: list[ForeignRaiseSite] = []
        self._scopes: list[ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef] = []

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scopes.append(node)
        self.generic_visit(node)
        self._scopes.pop()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scopes.append(node)
        self.generic_visit(node)
        self._scopes.pop()

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scopes.append(node)
        self.generic_visit(node)
        self._scopes.pop()

    @override
    def visit_Raise(self, node: ast.Raise) -> None:
        if node.exc is None:
            return
        class_name = _raised_class_name(node.exc)
        if class_name is None or class_name in self.root_names or self._is_allowed(class_name=class_name):
            return
        function = ".".join(scope.name for scope in self._scopes) or "<module>"
        self.sites.append(ForeignRaiseSite(path=self.path, function=function, exception=class_name, line=node.lineno))

    def _is_allowed(self, *, class_name: str) -> bool:
        if class_name in FRAMEWORK_CARRIER_NAMES:
            return True
        functions = [scope for scope in self._scopes if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if not functions:
            return False
        innermost = functions[-1]
        if innermost.name in DATA_MODEL_DUNDER_NAMES:
            return True
        decorators = _decorator_names(innermost)
        if decorators & VALIDATOR_DECORATOR_NAMES and class_name in VALIDATOR_EXCEPTION_NAMES:
            return True
        if class_name == "NotImplementedError":
            if "abstractmethod" in decorators:
                return True
            enclosing_classes = [scope for scope in self._scopes if isinstance(scope, ast.ClassDef)]
            if enclosing_classes and "Protocol" in {_expression_name(base) for base in enclosing_classes[-1].bases}:
                return True
        return False


def iter_foreign_raise_sites(*, path: str, source: str, root_names: frozenset[str]) -> list[ForeignRaiseSite]:
    """Every raise in a module of a class outside the root that no allowance covers.

    Args:
        path: The module's path, as the baseline names it.
        source: The module's source.
        root_names: The names of the root and of every class deriving from it.

    Returns:
        The sites, in the module's order.
    """
    visitor = _ForeignRaiseVisitor(path=path, root_names=root_names)
    visitor.visit(ast.parse(source, filename=path))
    return visitor.sites


def is_exempt_path(*, relative_parts: tuple[str, ...]) -> bool:
    """Whether a module lies in developer, release, migration or test code, which the check does not read."""
    return not EXEMPT_DIRECTORY_NAMES.isdisjoint(relative_parts)
