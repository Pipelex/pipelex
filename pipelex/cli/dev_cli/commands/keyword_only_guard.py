"""Pure-stdlib AST core for the keyword-only-arguments convention guard.

Non-subject function parameters must be keyword-only so call sites are self-documenting:
``do_thing(retries=3, timeout=30)`` is forced over the opaque ``do_thing(3, 30)``. The canonical
human-readable specification lives in ``docs/contribute/keyword-only-arguments.md``.

This module holds the AST collection logic that mechanically enforces the convention. It depends
on **stdlib only** (``ast``/``re``/``pathlib``) — no ``rich``, ``pipelex.hub``, or ``typer`` — so it
can be loaded in two cold-start budgets:

- The full-tree command (``pipelex-dev check-keyword-only``) imports from here and adds the
  ``rich``/``pipelex.hub`` presentation layer (see ``check_keyword_only_cmd.py``).
- The lean single-file entry below, invoked **by file path** (``python
  pipelex/cli/dev_cli/commands/keyword_only_guard.py <file>``), skips the whole Typer/hub import
  graph so a ``PostToolUse`` hook can check just the edited file in a few tens of milliseconds. Run
  by file path, not ``python -m ...`` — the ``-m`` form would import the ``pipelex`` package chain
  (``pipelex/__init__.py`` → ``rich``), defeating the cold-start budget.

Single-file results are an exact subset of the full scan: ``relative_path``/``module_qname`` are
computed identically (see ``collect_violations_for_files``), so the carve-out allowlist matches.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

# --------------------------------------------------------------------------------------
# Configuration / carve-out data
# --------------------------------------------------------------------------------------

#: Source root scanned by the guard (relative to the repo root / cwd).
SOURCE_ROOT = Path("pipelex")

#: Inline comment that suppresses a single violation on the def line it sits on.
ESCAPE_HATCH_MARKER = "# kw-only: ignore"

#: Anchored full-match against the function NAME node (not the source line).
#: The ``+`` quantifier guarantees a non-empty body so the degenerate ``____`` cannot match.
DUNDER_PATTERN = re.compile(r"__[A-Za-z0-9_]+__")

#: pydantic decorator names whose wrapped callables follow a fixed positional protocol.
PYDANTIC_DECORATOR_NAMES = frozenset(
    {
        "field_validator",
        "model_validator",
        "field_serializer",
        "model_serializer",
        "validator",
        "root_validator",
    }
)

#: Typer/click decorator attribute suffixes (receiver varies: app/graph_app/show_app/...).
TYPER_DECORATOR_ATTRS = frozenset({"command", "callback"})

#: Framework decorators matched on their bare name, so both ``@receiver.name`` and bare ``@name`` forms hit.
#: pytest's ``fixture`` is written both as ``@pytest.fixture`` and as bare ``@fixture`` (``from pytest import fixture``).
#: Jinja2's ``pass_context`` / ``pass_environment`` / ``pass_eval_context`` mark a filter/test/global whose
#: wrapped callable is invoked POSITIONALLY by the Jinja2 engine (``{{ x|filter(arg) }}``), so its arguments
#: cannot be made keyword-only — same framework-entrypoint category as Typer/Temporal/pytest. Written bare
#: (``@pass_context``, ``from jinja2 import pass_context``) or attributed (``@jinja2.pass_context``).
BARE_FRAMEWORK_DECORATOR_NAMES = frozenset({"fixture", "pass_context", "pass_environment", "pass_eval_context"})

#: Temporal handler decorators matched on their trailing two attribute segments.
TEMPORAL_DECORATOR_TAILS = frozenset(
    {
        ("activity", "defn"),
        ("workflow", "run"),
        ("workflow", "signal"),
        ("workflow", "query"),
        ("workflow", "update"),
    }
)

#: Typer parameter-annotation metadata callables that mark a call-style CLI entrypoint.
TYPER_ANNOTATION_ATTRS = frozenset({"Argument", "Option"})

#: Curated symmetric-tuple allowlist — exempt ENTIRELY, keyed by (qualified_name, relative_path).
#: There is no pattern guessing; both the dotted name and the file path must match exactly.
SYMMETRIC_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        ("pipelex.system.environment.set_env", "pipelex/system/environment.py"),
        ("pipelex.kit.single_file_agent_rules.unified_diff", "pipelex/kit/single_file_agent_rules.py"),
        ("pipelex.tools.misc.diff.diff_files", "pipelex/tools/misc/diff.py"),
        ("pipelex.tools.misc.diff.diff_dirs", "pipelex/tools/misc/diff.py"),
        ("pipelex.tools.typing.class_utils.are_classes_equivalent", "pipelex/tools/typing/class_utils.py"),
    }
)


class Violation(NamedTuple):
    """A single keyword-only convention violation.

    Attributes:
        relative_path: The source file path relative to the repo root.
        qualified_name: Module-relative dotted path (package.module + class chain + function name).
        lineno: 1-based line of the ``def`` for human display only — never part of the stable key.
    """

    relative_path: str
    qualified_name: str
    lineno: int

    @property
    def key(self) -> str:
        """Stable identity key for sorting/dedup: ``<relative_path>::<qualified_function_name>`` (no line number)."""
        return f"{self.relative_path}::{self.qualified_name}"


# --------------------------------------------------------------------------------------
# Carve-out detection (pure AST, no import resolution)
# --------------------------------------------------------------------------------------


def _attribute_tail(node: ast.expr) -> tuple[str, ...]:
    """Return the trailing attribute segments of a dotted expression (e.g. ``a.b.c`` -> ``(a, b, c)``)."""
    segments: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        segments.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        segments.append(current.id)
    segments.reverse()
    return tuple(segments)


def _decorator_matches_carveout(decorator: ast.expr) -> bool:
    """Whether a single decorator expression matches any framework / pydantic carve-out."""
    target: ast.expr = decorator.func if isinstance(decorator, ast.Call) else decorator

    bare_name: str | None = None
    if isinstance(target, ast.Name):
        bare_name = target.id
    elif isinstance(target, ast.Attribute):
        bare_name = target.attr

    # Bare-name matches — valid whether the decorator is written bare (`@name`) or attributed (`@receiver.name`).
    if bare_name is not None:
        if bare_name in PYDANTIC_DECORATOR_NAMES:
            return True
        if bare_name in BARE_FRAMEWORK_DECORATOR_NAMES:
            return True
        if bare_name == "override":
            return True
    # Attribute-only matches — these framework decorators are always written as `receiver.attr`, never bare.
    if isinstance(target, ast.Attribute):
        if target.attr in TYPER_DECORATOR_ATTRS:
            return True
        tail = _attribute_tail(target)
        if len(tail) >= 2 and tail[-2:] in TEMPORAL_DECORATOR_TAILS:
            return True
    return False


def _has_carveout_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Scan the WHOLE decorator stack for a carve-out match (e.g. @activity.defn above @convert_pipelex_errors)."""
    return any(_decorator_matches_carveout(decorator) for decorator in node.decorator_list)


def _iter_subscript_metadata(annotation: ast.expr) -> Iterator[ast.expr]:
    """Yield the metadata elements of an ``Annotated[...]`` subscript (everything after the first slice element)."""
    if not isinstance(annotation, ast.Subscript):
        return
    slice_value = annotation.slice
    if isinstance(slice_value, ast.Tuple):
        yield from slice_value.elts[1:]


def _callee_name(func: ast.expr) -> str | None:
    """The trailing name of a call target: ``typer.Option`` -> ``Option``, bare ``Option`` -> ``Option``."""
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _annotation_has_typer_metadata(annotation: ast.expr | None) -> bool:
    """Whether an ``Annotated[...]`` annotation carries ``Argument(...)`` / ``Option(...)`` metadata.

    Matches the qualified ``typer.Argument(...)`` form and the bare ``Argument(...)`` form alike
    (``from typer import Argument``), so call-style CLI entrypoints are detected either way.
    """
    if annotation is None:
        return False
    for metadata in _iter_subscript_metadata(annotation):
        for sub_node in ast.walk(metadata):
            if isinstance(sub_node, ast.Call) and _callee_name(sub_node.func) in TYPER_ANNOTATION_ATTRS:
                return True
    return False


def _has_typer_param_annotation(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Detect call-style Typer entrypoints registered without a decorator (closes the decorator-blind gap)."""
    all_args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    return any(_annotation_has_typer_metadata(arg.annotation) for arg in all_args)


# --------------------------------------------------------------------------------------
# Rule evaluation
# --------------------------------------------------------------------------------------


def _positional_or_keyword_count(node: ast.FunctionDef | ast.AsyncFunctionDef, *, is_method: bool) -> int:
    """Count positional-or-keyword params after dropping self/cls and the allowed subject.

    Keyword-only params (already compliant) and ``*args``/``**kwargs`` are not counted.
    """
    params = [*node.args.posonlyargs, *node.args.args]
    if is_method and params and params[0].arg in {"self", "cls"}:
        params = params[1:]
    # Drop the single allowed subject under Exception 1.
    params = params[1:]
    return len(params)


def _is_dunder(name: str) -> bool:
    """Whether a function name is a reserved dunder (anchored full-match on the NAME only)."""
    return DUNDER_PATTERN.fullmatch(name) is not None


def _def_line_has_escape_hatch(node: ast.FunctionDef | ast.AsyncFunctionDef, *, source_lines: list[str]) -> bool:
    """Whether the ``# kw-only: ignore`` marker is present on the physical def header line."""
    index = node.lineno - 1
    if 0 <= index < len(source_lines):
        return ESCAPE_HATCH_MARKER in source_lines[index]
    return False


def _qualify(name: str, *, class_stack: tuple[str, ...], func_stack: tuple[str, ...]) -> str:
    """Build the module-relative dotted qualified name from the enclosing class/function stack."""
    return ".".join((*class_stack, *func_stack, name))


def _evaluate_def(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    module_qname: str,
    relative_path: str,
    class_stack: tuple[str, ...],
    func_stack: tuple[str, ...],
    is_method: bool,
    source_lines: list[str],
) -> Violation | None:
    """Apply the carve-outs then the rule to a single def; return a Violation or None."""
    # Carve-outs first — any match => skip entirely.
    if _is_dunder(node.name):
        return None
    if _def_line_has_escape_hatch(node, source_lines=source_lines):
        return None
    if _has_carveout_decorator(node):
        return None
    if _has_typer_param_annotation(node):
        return None

    local_qname = _qualify(node.name, class_stack=class_stack, func_stack=func_stack)
    dotted_qname = f"{module_qname}.{local_qname}"
    if (dotted_qname, relative_path) in SYMMETRIC_ALLOWLIST:
        return None

    # Rule: a bare `*` is required once two or more positional-or-keyword params remain
    # after dropping self/cls — i.e. at least one non-subject positional-or-keyword param.
    if _positional_or_keyword_count(node, is_method=is_method) >= 1:
        return Violation(relative_path=relative_path, qualified_name=local_qname, lineno=node.lineno)
    return None


class _Collector(ast.NodeVisitor):
    """Walks the module, tracking the enclosing class/function scope to qualify defs."""

    def __init__(self, *, module_qname: str, relative_path: str, source_lines: list[str]) -> None:
        self.module_qname = module_qname
        self.relative_path = relative_path
        self.source_lines = source_lines
        self.violations: list[Violation] = []
        self._class_stack: tuple[str, ...] = ()
        self._func_stack: tuple[str, ...] = ()
        self._in_class_body: tuple[bool, ...] = ()

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # ast visitor naming
        self._class_stack = (*self._class_stack, node.name)
        self._in_class_body = (*self._in_class_body, True)
        self.generic_visit(node)
        self._class_stack = self._class_stack[:-1]
        self._in_class_body = self._in_class_body[:-1]

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        is_method = bool(self._in_class_body) and self._in_class_body[-1]
        violation = _evaluate_def(
            node,
            module_qname=self.module_qname,
            relative_path=self.relative_path,
            class_stack=self._class_stack,
            func_stack=self._func_stack,
            is_method=is_method,
            source_lines=self.source_lines,
        )
        if violation is not None:
            self.violations.append(violation)
        # Descend into the function body; nested defs are NOT methods of the enclosing class.
        self._func_stack = (*self._func_stack, node.name)
        self._in_class_body = (*self._in_class_body, False)
        self.generic_visit(node)
        self._func_stack = self._func_stack[:-1]
        self._in_class_body = self._in_class_body[:-1]

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # ast visitor naming
        self._visit_function(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # ast visitor naming
        self._visit_function(node)


def find_violations_in_source(source: str, *, module_qname: str, relative_path: str) -> list[Violation]:
    """Find all keyword-only convention violations in a single Python source string.

    Args:
        source: The Python source text to scan.
        module_qname: The dotted module path used to qualify each def (e.g. ``pipelex.builder.foo``).
        relative_path: The source file path relative to the repo root (used in the violation's sort/identity key).

    Returns:
        The violations found, in source order.
    """
    tree = ast.parse(source)
    collector = _Collector(module_qname=module_qname, relative_path=relative_path, source_lines=source.splitlines())
    collector.visit(tree)
    return collector.violations


# --------------------------------------------------------------------------------------
# Filesystem walking
# --------------------------------------------------------------------------------------


def _module_qname_for(path: Path) -> str:
    """Compute the dotted module name for a ``.py`` file under the source root."""
    parts = list(path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def iter_source_files(root: Path) -> Iterator[Path]:
    """Yield every ``.py`` file under ``root``, excluding ``__pycache__``."""
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def collect_all_violations(root: Path) -> list[Violation]:
    """Scan every source file under ``root`` and return all violations, sorted by key."""
    violations: list[Violation] = []
    for path in iter_source_files(root):
        relative_path = path.as_posix()
        module_qname = _module_qname_for(path)
        source = path.read_text(encoding="utf-8")
        violations.extend(find_violations_in_source(source, module_qname=module_qname, relative_path=relative_path))
    return sorted(violations, key=lambda violation: violation.key)


# --------------------------------------------------------------------------------------
# Single-file scanning (lean hot path for the PostToolUse hook)
# --------------------------------------------------------------------------------------


def relative_source_path(path: Path, *, root: Path | None = None) -> Path | None:
    """Return ``path`` as a repo-root-relative ``Path`` iff it is an in-scope ``pipelex/`` source file.

    In-scope means: a ``.py`` file under ``SOURCE_ROOT`` (``pipelex/``), not inside ``__pycache__``.
    Anything else (out-of-tree path, non-``.py``, a sibling repo, a test file) returns ``None`` so the
    caller can pass any edited path and let this self-filter.

    Args:
        path: The edited path, absolute or relative to ``root``.
        root: The repo root; defaults to the current working directory (the hook runs from there).
    """
    base = root or Path.cwd()
    resolved = path if path.is_absolute() else base / path
    try:
        relative = resolved.resolve().relative_to(base.resolve())
    except ValueError:
        return None  # outside the repo
    if relative.suffix != ".py":
        return None
    if "__pycache__" in relative.parts:
        return None
    if not relative.parts or relative.parts[0] != SOURCE_ROOT.name:
        return None
    return relative


def collect_violations_for_files(paths: Iterable[Path], *, root: Path | None = None) -> list[Violation]:
    """Find violations across the given files; out-of-scope, missing, or unparseable files are skipped.

    Results are an exact subset of :func:`collect_all_violations`: ``relative_path`` and ``module_qname``
    are computed identically (the carve-out allowlist keys on both), so a single-file scan agrees with
    the full-tree scan for that file.

    A file that does not parse yet (``SyntaxError``) is skipped rather than reported — a mid-edit file
    is not a keyword-only violation, and the hook must never block on a transient syntax error.

    Args:
        paths: Edited paths, absolute or relative to ``root``.
        root: The repo root; defaults to the current working directory.
    """
    base = root or Path.cwd()
    violations: list[Violation] = []
    for path in paths:
        relative = relative_source_path(path, root=base)
        if relative is None:
            continue
        try:
            source = (base / relative).read_text(encoding="utf-8")
        except OSError:
            continue  # file vanished between the edit and the hook — nothing to check
        try:
            file_violations = find_violations_in_source(
                source,
                module_qname=_module_qname_for(relative),
                relative_path=relative.as_posix(),
            )
        except SyntaxError:
            continue  # not-yet-parseable mid-edit file is not a violation
        violations.extend(file_violations)
    return sorted(violations, key=lambda violation: violation.key)


def main(argv: list[str]) -> int:
    """Lean single-file entrypoint for the ``PostToolUse`` hook — stdlib only, no Typer/rich/hub.

    Usage (by file path, not ``-m`` — see the module docstring): ``python
    pipelex/cli/dev_cli/commands/keyword_only_guard.py <file> [<file> ...]``

    Prints any violations to ``stderr`` and returns ``2`` (so a hook blocks and feeds the list back to
    the agent); returns ``0`` when the in-scope files are clean or none are in scope. Plain ``print`` to
    stderr is intentional here — pulling in ``pipelex.log``/``rich`` would defeat the cold-start budget.
    """
    violations = collect_violations_for_files([Path(arg) for arg in argv])
    if not violations:
        return 0
    print("✗ Keyword-only violation(s) in edited pipelex source:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation.relative_path}:{violation.lineno}  {violation.qualified_name}", file=sys.stderr)
    print(
        "Place a bare `*` after the subject, or add `# kw-only: ignore` on the def line if justified — see docs/contribute/keyword-only-arguments.md",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
