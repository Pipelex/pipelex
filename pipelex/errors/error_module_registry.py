"""Registry of modules that define :class:`pipelex.base_exceptions.PipelexError` subclasses.

Importing this module force-loads every module known to declare a
``PipelexError`` subclass, so callers can rely on
:meth:`PipelexError.__subclasses__` returning the complete production hierarchy.
Two consumers depend on this guarantee:

- The ``pipelex-dev generate-error-pages`` command, which emits one docs page
  per subclass.
- The type-URI uniqueness test, which walks the full hierarchy to detect
  collisions in the docs URL keyspace.

Most subclasses live in ``exceptions.py`` modules — those are discovered via a
filesystem scan rooted at the ``pipelex`` package directory. A small explicit
list captures the few error classes that live in non-standard locations
(``system/environment.py``, ``tools/misc/toml_utils.py``, etc.) so they are
not silently missed when the docs are regenerated.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

import pipelex
from pipelex.base_exceptions import PipelexError

if TYPE_CHECKING:
    from collections.abc import Iterator

# Modules that define PipelexError subclasses but do not live in an
# ``exceptions.py`` file. Add to this list when a new error class is declared
# alongside non-error code (e.g. a tool module that raises its own error type).
_NON_STANDARD_ERROR_MODULES: tuple[str, ...] = (
    "pipelex.system.environment",
    "pipelex.tools.misc.toml_utils",
    "pipelex.tools.secrets.secrets_utils",
    "pipelex.pipe_operators.shared.template_image_analyzer",
)


def _discover_standard_exception_modules() -> tuple[str, ...]:
    """Return dotted module names for every conventionally-named error module under ``pipelex/``.

    Covers three filename conventions in use today:
    ``exceptions.py``, ``*_exceptions.py`` (plugin error modules), and ``*_errors.py``.
    Missing one of them previously made the docs generator depend on Pipelex
    bootstrap order to pick up plugin error classes — fragile coupling.
    """
    pipelex_root = Path(pipelex.__file__).resolve().parent
    repo_root = pipelex_root.parent
    discovered: set[str] = set()
    for pattern in ("exceptions.py", "*_exceptions.py", "*_errors.py"):
        for path in pipelex_root.rglob(pattern):
            rel = path.relative_to(repo_root).with_suffix("")
            discovered.add(".".join(rel.parts))
    return tuple(sorted(discovered))


def load_all_error_modules() -> None:
    """Force-import every module known to declare a ``PipelexError`` subclass.

    Idempotent — re-importing a module is a no-op for the Python interpreter.
    """
    for module_name in _discover_standard_exception_modules():
        importlib.import_module(module_name)
    for module_name in _NON_STANDARD_ERROR_MODULES:
        importlib.import_module(module_name)


def iter_pipelex_error_subclasses() -> Iterator[type[PipelexError]]:
    """Yield :class:`PipelexError` and every loaded subclass, breadth-first.

    Skips classes whose ``__module__`` starts with ``tests.`` so synthetic
    subclasses created by other tests in the same pytest session never leak
    into the generated docs or the smoke-test assertions.
    """
    load_all_error_modules()
    seen: set[type[PipelexError]] = set()
    stack: list[type[PipelexError]] = [PipelexError]
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        if not cls.__module__.startswith("tests."):
            yield cls
        stack.extend(cls.__subclasses__())
