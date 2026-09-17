"""AST core for the Rich import guard.

Rich is the ``cli`` extra: the ``pipelex`` and ``pipelex-agent`` CLIs install it, and a server installs
pipelex without it. What makes that safe is two rules, which this module checks mechanically:

1. **The direct rule. Outside ``pipelex/cli/``, no module imports Rich at module level.** Everything else
   that renders through Rich, the console log sink, the pretty-print engine's ``rich`` mode, the
   ``rendered_pretty`` renderings, the model listing and cost tables, imports it inside the function that
   renders, after checking it is installed, so importing any of those modules costs a server nothing.
2. **The transitive rule. Outside ``pipelex/cli/``, no module reaches Rich through a CLI module either.**
   A module that imports a CLI module at module level loads whatever that module imports, so a CLI module
   importing Rich at the top of its file puts Rich into every importer of it. The rule resolves the
   module-level import graph of ``pipelex/``, the one the hub-layering guard builds, and reports the
   shortest chain from the offending module to a CLI module that imports Rich, at the line of its first hop.

The human-readable specification lives in ``docs/contribute/rich-imports.md``.

"Module level" means what an ``import`` of the module executes. An import statement counts wherever it sits
outside a function body: at the top of the file, in a module-level ``try`` or ``if`` block, in a class
body. Two places are exempt, because nothing in them runs at import time: a function body, and the body
of an ``if TYPE_CHECKING:`` block (its ``else`` branch is runtime code and is checked). The import graph
shares those carve-outs, and one more: a statement carrying the hub-layering guard's own
``# hub-layering: ignore`` marker is no edge in it.

Both rules read source, so neither sees an import assembled at runtime. What pins the property itself, a
pipe run with Rich refused, is ``tests/integration/pipelex/test_rich_free_run.py``.

There is no escape hatch. A module that genuinely needs Rich at module level is a CLI module and belongs
under ``pipelex/cli/``.

This module depends on the stdlib and on the sibling ``hub_layering_guard``, whose import graph it reuses.
The presentation layer wired into the ``pipelex-dev`` Typer app lives in ``check_rich_imports_cmd.py``.
"""

from __future__ import annotations

import ast
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from typing_extensions import override

from pipelex.cli.dev_cli.commands.hub_layering_guard import ImportGraph, build_import_graph, module_qname_for

if TYPE_CHECKING:
    from collections.abc import Iterator

#: Source root the guard scans (relative to the repo root / cwd). Tests are not scanned: the suite
#: installs every extra.
SOURCE_ROOT = Path("pipelex")

#: The package allowed to import Rich at module level, as a repo-root-relative posix path prefix.
CLI_PACKAGE_PREFIX = "pipelex/cli/"

#: The top-level package the guard refuses at module level.
RICH_PACKAGE = "rich"

#: The ``typing.TYPE_CHECKING`` flag name, matched bare (``TYPE_CHECKING``) or attributed (``typing.TYPE_CHECKING``).
TYPE_CHECKING_NAME = "TYPE_CHECKING"

#: The only receiver the attributed form may be rooted at, so an unrelated ``x.TYPE_CHECKING`` earns no exemption.
TYPING_MODULE_NAME = "typing"

REMEDY = (
    "import Rich inside the function that renders, after `require_rich(...)` or `require_rich_for_rendering()`, "
    "and put a type-only import under `if TYPE_CHECKING:`; a module that reaches Rich through a CLI module "
    "defers that import into the function that needs it, or moves what it needs out of `pipelex/cli/`"
)

#: The calls that answer whether Rich is installed, so a deferred import below one of them is reached only
#: where Rich is there. ``require_rich`` and ``require_rich_for_rendering`` raise ``MissingDependencyError``
#: naming the extra; ``get_console`` hands out a console whose own construction raised it already;
#: ``is_rich_installed`` asks without importing, for a rendering that falls back instead of failing.
GUARD_CALL_NAMES = frozenset({"require_rich", "require_rich_for_rendering", "get_console", "is_rich_installed"})

#: The module the other fallback shape asks: ``if "rich" not in sys.modules: return None`` holds no Rich object
#: to render, and answers that without paying for an import.
SYS_MODULE_RECEIVER = "sys"
SYS_MODULES_ATTRIBUTE = "modules"


class RichImportGuardError(Exception):
    """The guard cannot run as configured: a self-check failure, never a violation.

    Kept local to this stdlib-only module rather than derived from ``PipelexError``, for the reason
    ``hub_layering_guard`` gives for its own.
    """


class RichImportViolation(NamedTuple):
    """One module-level Rich import, located for a report line."""

    relative_path: str
    lineno: int
    detail: str

    @property
    def key(self) -> str:
        """Stable sort key: file, then line."""
        return f"{self.relative_path}:{self.lineno:06d}"


def is_rich_module(*, module_name: str) -> bool:
    """Whether a dotted module name is Rich or inside it, matched on the package boundary (``richer`` is not Rich)."""
    return module_name == RICH_PACKAGE or module_name.startswith(f"{RICH_PACKAGE}.")


def is_allowed_path(*, relative_path: str) -> bool:
    """Whether a repo-root-relative posix path sits in the CLI package, which installs the ``cli`` extra."""
    return relative_path.startswith(CLI_PACKAGE_PREFIX)


def _is_type_checking_test(*, test: ast.expr) -> bool:
    """Whether an ``if`` test is the bare ``TYPE_CHECKING`` / ``typing.TYPE_CHECKING`` flag.

    Only the bare forms count: ``if not TYPE_CHECKING:`` guards a runtime branch and is not exempt.
    """
    match test:
        case ast.Name(id=name):
            return name == TYPE_CHECKING_NAME
        case ast.Attribute(value=ast.Name(id=receiver), attr=attr):
            return receiver == TYPING_MODULE_NAME and attr == TYPE_CHECKING_NAME
        case _:
            return False


class _ModuleLevelRichImportCollector(ast.NodeVisitor):
    """Walks the statements an import of one module executes, recording every Rich import among them."""

    def __init__(self, *, relative_path: str) -> None:
        self.relative_path = relative_path
        self.violations: list[RichImportViolation] = []

    def _record(self, *, node: ast.Import | ast.ImportFrom, module_name: str) -> None:
        self.violations.append(
            RichImportViolation(relative_path=self.relative_path, lineno=node.lineno, detail=f"imports `{module_name}` at module level")
        )

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        """A function body runs when the function is called, not when the module is imported."""

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        """A coroutine body runs when the coroutine is awaited, not when the module is imported."""

    @override
    def visit_If(self, node: ast.If) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        """Skip the body of ``if TYPE_CHECKING:``; its ``else`` branch is ordinary runtime code."""
        if not _is_type_checking_test(test=node.test):
            self.generic_visit(node)
            return
        for statement in node.orelse:
            self.visit(statement)

    @override
    def visit_Import(self, node: ast.Import) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        """``import rich`` / ``import rich.console as console``."""
        for alias in node.names:
            if is_rich_module(module_name=alias.name):
                self._record(node=node, module_name=alias.name)
                return

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        """``from rich.console import Console`` / ``from rich import box``. A relative import is never Rich."""
        if node.level == 0 and node.module is not None and is_rich_module(module_name=node.module):
            self._record(node=node, module_name=node.module)


def _module_level_rich_imports(*, source: str, relative_path: str) -> list[RichImportViolation]:
    """Every module-level Rich import in one module's source, wherever the module sits."""
    collector = _ModuleLevelRichImportCollector(relative_path=relative_path)
    collector.visit(ast.parse(source))
    return sorted(collector.violations, key=lambda violation: violation.key)


def _called_name(*, func: ast.expr) -> str | None:
    """The bare name a call is made through: ``require_rich(...)`` and ``self.require_rich(...)`` both answer the same."""
    match func:
        case ast.Name(id=name):
            return name
        case ast.Attribute(attr=attr):
            return attr
        case _:
            return None


def _is_sys_modules(*, node: ast.AST) -> bool:
    """Whether a node is the ``sys.modules`` mapping itself."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == SYS_MODULES_ATTRIBUTE
        and isinstance(node.value, ast.Name)
        and node.value.id == SYS_MODULE_RECEIVER
    )


def _mentions_a_guard(*, node: ast.AST) -> bool:
    """Whether one expression asks whether Rich is available, by a guard call or by the ``sys.modules`` mapping."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and _called_name(func=child.func) in GUARD_CALL_NAMES:
            return True
        if _is_sys_modules(node=child):
            return True
    return False


def _establishes_rich_is_available(*, statement: ast.stmt) -> bool:
    """Whether one statement asks whether Rich is available, so that what follows it may import Rich.

    The question is asked of the statement itself, not of the branches it opens: an ``if`` is read by its
    condition, so ``if "rich" not in sys.modules: return None`` and ``if is_rich_installed():`` both count,
    and a guard *call* buried inside a branch counts for that branch and its sequel rather than for the
    statements above it. That is deliberately permissive — it settles that the question was asked, not that
    every path through the answer is sound. What pins the property itself is the Rich-refused pipe run in
    ``tests/integration/pipelex/test_rich_free_run.py``.
    """
    match statement:
        case ast.If(test=test) | ast.While(test=test):
            return _mentions_a_guard(node=test)
        case ast.For() | ast.AsyncFor() | ast.With() | ast.AsyncWith() | ast.Try() | ast.ClassDef():
            return False
        case _:
            return _mentions_a_guard(node=statement)


def _nested_bodies(*, statement: ast.stmt) -> Iterator[list[ast.stmt]]:
    """The statement lists one compound statement runs, excluding an ``if TYPE_CHECKING:`` body, which never runs."""
    match statement:
        case ast.If(test=test, body=then, orelse=otherwise):
            if _is_type_checking_test(test=test):
                yield otherwise
                return
            yield then
            yield otherwise
        case ast.For(body=then, orelse=otherwise) | ast.AsyncFor(body=then, orelse=otherwise) | ast.While(body=then, orelse=otherwise):
            yield then
            yield otherwise
        case ast.With(body=then) | ast.AsyncWith(body=then) | ast.ClassDef(body=then):
            yield then
        case ast.Try(body=then, handlers=handlers, orelse=otherwise, finalbody=finally_):
            yield then
            for handler in handlers:
                yield handler.body
            yield otherwise
            yield finally_
        case _:
            return


def _rich_import_in(*, statement: ast.stmt) -> str | None:
    """The Rich module one import statement names, or ``None`` for any other statement."""
    match statement:
        case ast.Import(names=names):
            return next((alias.name for alias in names if is_rich_module(module_name=alias.name)), None)
        case ast.ImportFrom(level=0, module=str() as module) if is_rich_module(module_name=module):
            return module
        case _:
            return None


def _unguarded_deferred_rich_imports(*, source: str, relative_path: str) -> list[RichImportViolation]:
    """Every deferred Rich import that nothing above it in its own function established Rich for.

    Deferring the import is the direct rule's business; this is the other half of the same contract, the one
    that turns a bare ``ModuleNotFoundError`` into the ``MissingDependencyError`` that names the extra.
    """
    violations: list[RichImportViolation] = []
    for function in _function_scopes(tree=ast.parse(source)):
        violations.extend(_unguarded_in_block(body=function.body, guarded=False, function_name=function.name, relative_path=relative_path))
    return violations


def _unguarded_in_block(*, body: list[ast.stmt], guarded: bool, function_name: str, relative_path: str) -> list[RichImportViolation]:
    """Walk one block in order, carrying whether something above already asked that Rich is available.

    A guard reaches everything after it in its own block and everything nested inside those statements; it
    does not reach backwards, and it does not reach out of the branch it sits in. A nested ``def`` is skipped,
    being a scope of its own with a guard of its own: its body runs when it is called, not here.
    """
    violations: list[RichImportViolation] = []
    for statement in body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        module_name = _rich_import_in(statement=statement)
        if module_name is not None and not guarded:
            violations.append(
                RichImportViolation(
                    relative_path=relative_path,
                    lineno=statement.lineno,
                    detail=f"imports `{module_name}` inside `{function_name}` with no `require_rich(...)` above it",
                )
            )
        guarded_here = guarded or _establishes_rich_is_available(statement=statement)
        for nested in _nested_bodies(statement=statement):
            violations.extend(_unguarded_in_block(body=nested, guarded=guarded_here, function_name=function_name, relative_path=relative_path))
        guarded = guarded_here
    return violations


def _function_scopes(*, tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function and coroutine in one module, at any depth, each yielded once."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def find_violations_in_source(*, source: str, relative_path: str) -> list[RichImportViolation]:
    """Scan one module's source and return its module-level Rich imports, or none for a CLI module.

    Args:
        source: The module's full source text.
        relative_path: Its repo-root-relative posix path, which decides whether it is a CLI module.

    Raises:
        SyntaxError: If the source does not parse. Never swallowed: an unparseable module in the scanned
            tree would otherwise be a blind spot.
    """
    if is_allowed_path(relative_path=relative_path):
        return []
    violations = _module_level_rich_imports(source=source, relative_path=relative_path)
    violations.extend(_unguarded_deferred_rich_imports(source=source, relative_path=relative_path))
    return sorted(violations, key=lambda violation: violation.key)


def shortest_chain_to_any(*, graph: ImportGraph, start: str, targets: frozenset[str]) -> list[str]:
    """The shortest module-level import chain from ``start`` to any module of ``targets``, or ``[]`` if none.

    One breadth-first walk per start rather than one per target, since a CLI module that imports Rich is
    one of many. Among chains of equal length the next hop is picked in module-name order, so the report
    is deterministic; cutting one chain may leave another, which the next run reports in turn.
    """
    previous: dict[str, str] = {}
    seen = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for module in sorted(graph.edges.get(current, {})):
            if module in seen:
                continue
            previous[module] = current
            if module in targets:
                chain = [module]
                while chain[-1] != start:
                    chain.append(previous[chain[-1]])
                return list(reversed(chain))
            seen.add(module)
            queue.append(module)
    return []


def find_transitive_violations(*, graph: ImportGraph, rich_importers: frozenset[str]) -> list[RichImportViolation]:
    """Every module outside the CLI package that reaches a CLI module importing Rich, through module-level imports.

    Args:
        graph: The module-level import graph of the source tree.
        rich_importers: The dotted names of the CLI modules that import Rich at module level. A module outside
            the CLI that imports Rich itself is the direct rule's finding, and its importers are not reported
            again here: removing that one import is the fix for all of them.
    """
    violations: list[RichImportViolation] = []
    for qname, path in sorted(graph.paths.items()):
        relative_path = path.as_posix()
        if is_allowed_path(relative_path=relative_path):
            continue
        chain = shortest_chain_to_any(graph=graph, start=qname, targets=rich_importers)
        if not chain:
            continue
        first_hop = chain[1]
        violations.append(
            RichImportViolation(
                relative_path=relative_path,
                lineno=graph.edges[qname][first_hop],
                detail=f"reaches Rich via {' → '.join(chain[1:])}, which imports it at module level",
            )
        )
    return violations


def iter_source_files(*, root: Path) -> Iterator[Path]:
    """Yield every ``.py`` file under ``root``, excluding ``__pycache__``."""
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def collect_violations(*, root: Path) -> list[RichImportViolation]:
    """Scan every ``.py`` file under ``root`` and return the violations of both rules, sorted by location.

    Args:
        root: The source root, relative to the repo root: the allowlist is matched on the paths it yields,
            and the import graph derives module names from them.

    Raises:
        RichImportGuardError: If the scan finds no module, or none under the CLI package, or an import graph
            that does not hold the modules the scan read. Each means the root is not the repo-root-relative
            ``pipelex`` the allowlist and the module names are written against, and the guard would
            otherwise report a pass having checked nothing, or everything.
    """
    violations: list[RichImportViolation] = []
    rich_importers: set[str] = set()
    nb_modules = 0
    nb_cli_modules = 0
    for path in iter_source_files(root=root):
        relative_path = path.as_posix()
        nb_modules += 1
        source = path.read_text(encoding="utf-8")
        rich_imports = _module_level_rich_imports(source=source, relative_path=relative_path)
        if is_allowed_path(relative_path=relative_path):
            nb_cli_modules += 1
            # Only a module-level import puts Rich into this module's importers: a deferred one runs on a call.
            if rich_imports:
                rich_importers.add(module_qname_for(path=path))
        else:
            violations.extend(rich_imports)
            violations.extend(_unguarded_deferred_rich_imports(source=source, relative_path=relative_path))
    if nb_modules == 0 or nb_cli_modules == 0:
        msg = (
            f"the Rich import guard scanned {nb_modules} module(s) under `{root}`, {nb_cli_modules} of them under "
            f"`{CLI_PACKAGE_PREFIX}`, so its allowlist matched nothing. Run it from the repo root with the "
            f"repo-root-relative `{SOURCE_ROOT}` root, or update CLI_PACKAGE_PREFIX if the CLI package moved."
        )
        raise RichImportGuardError(msg)

    graph = build_import_graph(root=root)
    if len(graph.paths) != nb_modules or not rich_importers <= graph.paths.keys():
        msg = (
            f"the Rich import guard's import graph holds {len(graph.paths)} module(s) where the scan read {nb_modules}, "
            f"so the transitive rule would walk a different tree than the direct rule checked."
        )
        raise RichImportGuardError(msg)
    violations.extend(find_transitive_violations(graph=graph, rich_importers=frozenset(rich_importers)))
    return sorted(violations, key=lambda violation: violation.key)
