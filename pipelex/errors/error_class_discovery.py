"""Discovery of every ``PipelexError`` subclass the package defines.

The committed wire-identity snapshot (:mod:`pipelex.errors.error_identity_snapshot`), the
``type_uri`` uniqueness check and the error-class location convention all need the complete set of
error classes, including the ones whose module only a deferred plugin or factory import would reach.
:func:`iter_pipelex_error_subclasses` gives them that set, without bootstrapping Pipelex.
"""

from __future__ import annotations

import functools
import importlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pipelex
from pipelex.base_exceptions import PipelexError

if TYPE_CHECKING:
    from collections.abc import Iterator


_PIPELEX_ROOT = Path(pipelex.__file__).resolve().parent
_FIXTURE_DIR_NAMES = frozenset({"test_extras", "test_helpers"})


@functools.cache
def _force_load_all_error_modules() -> None:
    """Force-import every ``exceptions.py`` / ``*_exceptions.py`` module under ``pipelex/``.

    Cached via :func:`functools.cache` so the first call walks the package and
    ``importlib.import_module``-s every properly-named error module while
    subsequent calls are no-ops. Two preconditions keep this safe and complete,
    both enforced by
    ``tests/unit/pipelex/errors/test_error_class_location_convention.py``:

    1. Every :class:`PipelexError` subclass lives in a module named
       ``exceptions.py`` or ``<topic>_exceptions.py``. A name-filtered ``rglob``
       therefore captures the complete error-class set, with no allowlist.
    2. Every properly-named error module imports only base error classes
       (``PipelexError`` / ``CogtError`` / ``CredentialsError`` /
       ``ClickException``) and no third-party SDK. Force-loading adds no
       optional-plugin weight to pytest collection or dev CLI invocations.

    Production code (notably ``Pipelex.make()``) does NOT touch this: discovery
    has no runtime side effect outside the dev and test consumers.

    Per-module import failures are accumulated and raised once at the end so a
    single broken ``*_exceptions.py`` surfaces with its dotted module name
    rather than aborting the walk under an opaque exception whose traceback
    frames all live inside this helper. ``functools.cache`` only memoizes the
    success path (no caching on exception), so a fix-then-retry cycle inside
    a long-lived dev session works without ``cache_clear()``.

    The catch is intentionally broad: ``importlib.import_module`` runs the
    target module's top-level code, so a typo or bad reference inside a new
    ``*_exceptions.py`` can surface as ``NameError``, ``SyntaxError``,
    ``AttributeError``, … — all of which must be aggregated like ``ImportError``
    so the dev sees the full list of broken modules at once.
    """
    failures: list[tuple[str, BaseException]] = []
    for path in sorted(_PIPELEX_ROOT.rglob("*.py")):
        name = path.name
        if name != "exceptions.py" and not name.endswith("_exceptions.py"):
            continue
        rel = path.relative_to(_PIPELEX_ROOT.parent).with_suffix("")
        dotted = ".".join(rel.parts)
        try:
            importlib.import_module(dotted)
        except Exception as exc:  # ruff: ignore[blind-except]
            # importlib runs the target module's top-level code — an open-ended exception surface
            # (NameError, SyntaxError, …) that must be aggregated like ImportError so the dev
            # sees the full list of broken modules at once instead of aborting on the first one.
            failures.append((dotted, exc))
    if failures:
        lines = ["One or more error modules failed to import during discovery:"]
        lines.extend(f"  - {name}: {exc}" for name, exc in failures)
        msg = "\n".join(lines)
        # Chain from the first failure so the dev sees a full traceback (file:line
        # of the broken module) in addition to the aggregated list of names —
        # str(exc) alone elides where the failure happened.
        raise RuntimeError(msg) from failures[0][1]


def _is_production_subclass(cls: type[PipelexError]) -> bool:
    """True when ``cls`` should appear in the production discovery set.

    Excludes synthetic subclasses created inside test modules (``tests.*``) and
    classes defined inside shipped fixture packages (``pipelex/.../test_extras/``,
    ``pipelex/.../test_helpers/``) — those are test infrastructure that happens
    to be packaged alongside production code so it can be reused across
    downstream test suites.
    """
    if cls.__module__.startswith("tests."):
        return False
    module = sys.modules.get(cls.__module__)
    if module is None:
        return True
    module_file = getattr(module, "__file__", None)
    if module_file is None:
        return True
    try:
        rel = Path(module_file).resolve().relative_to(_PIPELEX_ROOT)
    except ValueError:
        return True
    return _FIXTURE_DIR_NAMES.isdisjoint(rel.parts)


def iter_pipelex_error_subclasses() -> Iterator[type[PipelexError]]:
    """Yield :class:`PipelexError` and every loaded subclass, breadth-first.

    Calls :func:`_force_load_all_error_modules` first so deferred-import
    plugin / factory error modules are reachable via ``__subclasses__()``. The
    call is idempotent — first invocation walks the filesystem, subsequent
    invocations are no-ops.

    Skips classes that fail :func:`_is_production_subclass` so synthetic
    subclasses created by other tests in the same pytest session and classes
    defined under shipped fixture packages (``pipelex/.../test_extras/`` /
    ``test_helpers/``) never leak into the snapshot or the checks.
    """
    _force_load_all_error_modules()
    seen: set[type[PipelexError]] = set()
    stack: list[type[PipelexError]] = [PipelexError]
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        if _is_production_subclass(cls):
            yield cls
        stack.extend(cls.__subclasses__())
