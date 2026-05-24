"""Static check: every ``PipelexError`` subclass must live in a properly-named module.

Three complementary checks:

- **AST scan** — parses every ``.py`` file under ``pipelex/`` and resolves the
  transitive ``PipelexError`` descendant set by class-name graph traversal.
  Catches new error classes that land outside the convention even if the
  module is never imported by production code.
- **Runtime location check** — after normal imports finish, walks
  ``PipelexError.__subclasses__()`` transitively and asserts each subclass's
  ``__module__`` resolves to a properly-named file. Catches dynamic /
  decorator-registered cases the AST scan would miss.
- **Discovery completeness** — asserts the AST-discovered set of production
  subclass names equals the runtime-loaded set after the docs-generation
  bootstrap path runs. This is the regression net for the
  "natural-imports-reach-every-error-module" premise. If a properly-named
  ``exceptions.py`` exists on disk but no production import path pulls it in
  (e.g. plugin worker modules that defer their imports), the class is missing
  from ``PipelexError.__subclasses__()`` and this assertion fails loudly —
  which is exactly the silent-drift bug the refactor was meant to prevent.

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
from pipelex.errors.error_pages_generator import iter_pipelex_error_subclasses

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


def _ast_discover_pipelex_error_subclasses() -> dict[str, list[Path]]:
    """AST-scan ``pipelex/`` and return ``{class_name: [paths_where_defined]}`` for every transitive ``PipelexError`` subclass.

    Uses name-based BFS — a class is in the derived set if any of its bases'
    short names is already in the set. False positives are possible if a
    truly unrelated class shares a short name with a ``PipelexError``
    descendant; today none exist in the tree.
    """
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

    # PipelexError itself is the root, not a "discovered subclass" — drop it.
    derived.discard("PipelexError")
    return {name: class_to_files[name] for name in derived}


class TestErrorClassLocationConvention:
    def test_ast_scan_every_pipelex_error_subclass_lives_in_a_properly_named_module(self) -> None:
        """AST-scan ``pipelex/`` and assert every transitive ``PipelexError`` subclass lives in an accepted module."""
        ast_discovered = _ast_discover_pipelex_error_subclasses()

        misplaced: list[tuple[str, Path]] = []
        for class_name in sorted(ast_discovered):
            for path in ast_discovered[class_name]:
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
        """Walk ``PipelexError.__subclasses__()`` after the discovery helper fires and assert every loaded subclass lives in an accepted module."""
        # Trigger the Phase 7 discovery helper so the runtime set matches the AST set.
        # Without this, the test silently runs against only the naked-import
        # subclasses, which all happen to be convention-compliant — green for the
        # wrong reason.
        list(iter_pipelex_error_subclasses())

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

    def test_runtime_walk_discovers_every_ast_classified_subclass(self) -> None:
        """Discovery completeness: AST-discovered subclasses are reachable via ``__subclasses__()`` after the discovery helper runs.

        Failing here means a properly-named ``exceptions.py`` exists on disk but
        the discovery helper did not import it — the symptom that previously
        shipped as silently-dropped docs pages and missed ``type_uri``
        uniqueness checks. The Phase 7 fix wires
        :func:`_force_load_all_error_modules` into ``iter_pipelex_error_subclasses``
        so every AST-discovered class is reachable at runtime; this is a
        one-sided subset check (runtime ⊇ AST) — runtime-only classes
        (e.g. dynamically constructed via ``type()``) are intentionally
        allowed and not caught here.
        """
        ast_names = set(_ast_discover_pipelex_error_subclasses().keys())
        runtime_names = {cls.__name__ for cls in iter_pipelex_error_subclasses()} - {"PipelexError"}

        missing = ast_names - runtime_names
        if missing:
            lines = [
                "Discovery gap — AST-found subclasses that are not loaded at runtime:",
                "",
                *(f"  - {name}" for name in sorted(missing)),
                "",
                "These classes live in properly-named modules but no production code path imports them.",
                "Docs generation and the type_uri uniqueness check therefore silently miss them.",
            ]
            raise AssertionError("\n".join(lines))

    def test_no_heavy_third_party_imports_in_error_modules(self) -> None:
        """Every exceptions.py / *_exceptions.py imports only base error classes — no SDK pulls.

        Phase 7's discovery helper force-loads every match. If a *_exceptions.py
        were to import a plugin SDK (anthropic, boto3, openai, mistralai, google-genai,
        portkey-ai, azure-identity, pypdfium2, fal-client, etc.), the SDK would be
        pulled into every pytest collection and every dev CLI invocation — defeating
        the deferred-import design that keeps optional plugin deps optional.
        """
        forbidden_top_level = {
            "anthropic",
            "boto3",
            "botocore",
            "openai",
            "mistralai",
            "google",
            "portkey_ai",
            "azure",
            "pypdfium2",
            "fal_client",
        }
        offenders: list[tuple[Path, str]] = []
        for path in sorted(_PIPELEX_ROOT.rglob("*.py")):
            if path.name != "exceptions.py" and not path.name.endswith("_exceptions.py"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".", 1)[0]
                        if root in forbidden_top_level:
                            offenders.append((path, alias.name))
                elif isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".", 1)[0]
                    if root in forbidden_top_level:
                        offenders.append((path, node.module))
        if offenders:
            lines = ["Error modules import third-party SDKs — would slow every CI run:", ""]
            for path, name in offenders:
                lines.append(f"  - {path.relative_to(_PIPELEX_ROOT.parent)}: {name}")
            raise AssertionError("\n".join(lines))
