"""Static check: every ``PipelexError`` subclass must live in a properly-named module.

Two complementary checks:

- **AST scan** — parses every ``.py`` file under ``pipelex/`` and resolves the
  transitive ``PipelexError`` descendant set by class-name graph traversal.
  Catches new error classes that land outside the convention even if the
  module is never imported by production code.
- **Runtime backstop** — after normal imports finish, walks
  ``PipelexError.__subclasses__()`` transitively and asserts each subclass's
  ``__module__`` resolves to a properly-named file. Catches dynamic /
  decorator-registered cases the AST scan would miss, and is the regression
  net once ``error_module_registry.py`` is gone.

The accepted filename patterns are ``exceptions.py`` (default — one per
package directory) and ``<topic>_exceptions.py`` (for directories that host
multiple separate-concern error modules — see ``pipelex/plugins/*/``). The
root ``pipelex/base_exceptions.py`` is special-cased.
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pipelex
from pipelex.base_exceptions import PipelexError

_PIPELEX_ROOT: Path = Path(pipelex.__file__).resolve().parent
_BASE_EXCEPTIONS_FILE: Path = _PIPELEX_ROOT / "base_exceptions.py"


def _is_properly_named(path: Path) -> bool:
    """Return True if ``path`` matches the error-class location convention."""
    if path == _BASE_EXCEPTIONS_FILE:
        return True
    name = path.name
    return name == "exceptions.py" or name.endswith("_exceptions.py")


def _base_short_name(node: ast.expr) -> str | None:
    """Return the last attribute of a class base expression, or ``None`` if unresolvable.

    ``Foo`` → ``"Foo"``; ``mod.Foo`` → ``"Foo"``; ``mod.sub.Foo`` → ``"Foo"``;
    ``Foo[T]`` (a Subscript) → ``"Foo"``. Anything more exotic (a call, a
    lambda) yields ``None`` — those don't appear in our hierarchy.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_short_name(node.value)
    return None


class TestErrorClassLocationConvention:
    def test_ast_scan_every_pipelex_error_subclass_lives_in_a_properly_named_module(self) -> None:
        """AST-scan ``pipelex/`` and assert every transitive ``PipelexError`` subclass lives in an accepted module."""
        class_to_files: dict[str, list[Path]] = {}
        class_to_bases: dict[str, set[str]] = {}

        for path in sorted(_PIPELEX_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                class_to_files.setdefault(node.name, []).append(path)
                bases = class_to_bases.setdefault(node.name, set())
                for base in node.bases:
                    resolved = _base_short_name(base)
                    if resolved is not None:
                        bases.add(resolved)

        derived: set[str] = {"PipelexError"}
        while True:
            added = False
            for class_name, bases in class_to_bases.items():
                if class_name in derived:
                    continue
                if bases & derived:
                    derived.add(class_name)
                    added = True
            if not added:
                break

        misplaced: list[tuple[str, Path]] = []
        for class_name in sorted(derived):
            for path in class_to_files.get(class_name, []):
                if not _is_properly_named(path):
                    misplaced.append((class_name, path))

        if misplaced:
            lines = [
                "Found PipelexError subclasses outside the accepted module naming convention.",
                "Accepted filenames: exceptions.py, <topic>_exceptions.py (plus the special pipelex/base_exceptions.py root).",
                "",
            ]
            for class_name, path in misplaced:
                lines.append(f"  - {class_name}  →  {path.relative_to(_PIPELEX_ROOT.parent)}")
            raise AssertionError("\n".join(lines))

    def test_runtime_subclasses_walk_every_loaded_pipelex_error_subclass_lives_in_a_properly_named_module(self) -> None:
        """Walk ``PipelexError.__subclasses__()`` transitively and assert every loaded subclass lives in an accepted module."""
        seen: set[type[PipelexError]] = set()
        stack: list[type[PipelexError]] = [PipelexError]
        misplaced: list[tuple[str, str]] = []

        while stack:
            cls = stack.pop()
            if cls in seen:
                continue
            seen.add(cls)
            stack.extend(cls.__subclasses__())
            if cls is PipelexError:
                continue
            if cls.__module__.startswith("tests."):
                continue
            module = sys.modules.get(cls.__module__)
            if module is None:
                continue
            module_file = inspect.getsourcefile(module)
            if module_file is None:
                continue
            path = Path(module_file).resolve()
            if not _is_properly_named(path):
                misplaced.append((cls.__name__, str(path.relative_to(_PIPELEX_ROOT.parent))))

        if misplaced:
            lines = [
                "Loaded PipelexError subclasses live outside the accepted module naming convention.",
                "Accepted filenames: exceptions.py, <topic>_exceptions.py (plus the special pipelex/base_exceptions.py root).",
                "",
            ]
            for class_name, location in misplaced:
                lines.append(f"  - {class_name}  →  {location}")
            raise AssertionError("\n".join(lines))
