"""Command enforcing the keyword-only-arguments convention across ``pipelex/`` source.

Non-subject function parameters must be keyword-only so call sites are self-documenting:
``do_thing(retries=3, timeout=30)`` is forced over the opaque ``do_thing(3, 30)``.

The canonical human-readable specification lives in ``wip/keyword-only-args/convention.md``.
This module is the AST guard that mechanically enforces it.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rich.markup import escape
from rich.panel import Panel
from typing_extensions import override

from pipelex.hub import get_console

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

# --------------------------------------------------------------------------------------
# Configuration / carve-out data
# --------------------------------------------------------------------------------------

#: Source root scanned by the guard (relative to the repo root / cwd).
SOURCE_ROOT = Path("pipelex")

#: Baseline file: newline-delimited ``relpath::qualified_name`` keys, sorted, no line numbers.
BASELINE_PATH = Path("wip/keyword-only-args/violations-baseline.txt")

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
    }
)


@dataclass(frozen=True)
class Violation:
    """A single keyword-only convention violation.

    Attributes:
        relative_path: The source file path relative to the repo root.
        qualified_name: Module-relative dotted path (package.module + class chain + function name).
        lineno: 1-based line of the ``def`` for human display only — never part of the baseline key.
    """

    relative_path: str
    qualified_name: str
    lineno: int

    @property
    def key(self) -> str:
        """Stable baseline key: ``<relative_path>::<qualified_function_name>`` (no line number)."""
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
        relative_path: The source file path relative to the repo root (used in the baseline key).

    Returns:
        The violations found, in source order.
    """
    tree = ast.parse(source)
    collector = _Collector(module_qname=module_qname, relative_path=relative_path, source_lines=source.splitlines())
    collector.visit(tree)
    return collector.violations


# --------------------------------------------------------------------------------------
# Filesystem walking + baseline
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


def partition_violations(violations: list[Violation], *, baseline: set[str]) -> tuple[list[Violation], list[Violation]]:
    """Split violations into (known, new) relative to a baseline key set."""
    known: list[Violation] = []
    new: list[Violation] = []
    for violation in violations:
        if violation.key in baseline:
            known.append(violation)
        else:
            new.append(violation)
    return known, new


def load_baseline(path: Path) -> set[str]:
    """Read the baseline file into a set of keys; an absent file is an empty baseline."""
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def write_baseline(path: Path, *, keys: Iterable[str]) -> None:
    """Write the baseline file: sorted, newline-delimited, deduplicated keys."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_keys = sorted(set(keys))
    path.write_text("\n".join(sorted_keys) + ("\n" if sorted_keys else ""), encoding="utf-8")


# --------------------------------------------------------------------------------------
# Command entrypoint
# --------------------------------------------------------------------------------------


def _print_report(violations: list[Violation]) -> None:
    """Print the full inventory grouped by top-level package."""
    console = get_console()
    grouped: dict[str, list[Violation]] = {}
    for violation in violations:
        package = violation.relative_path.split("/")[1] if "/" in violation.relative_path else violation.relative_path
        grouped.setdefault(package, []).append(violation)
    console.print()
    console.print("[bold]Keyword-only convention — full inventory[/bold]")
    console.print()
    for package in sorted(grouped):
        package_violations = grouped[package]
        console.print(f"[bold cyan]{escape(package)}[/bold cyan] ([dim]{len(package_violations)}[/dim])")
        for violation in package_violations:
            console.print(f"  {escape(violation.relative_path)}:{violation.lineno}  [dim]{escape(violation.qualified_name)}[/dim]")
        console.print()
    console.print(f"[bold]Total:[/bold] {len(violations)}")
    console.print()


def check_keyword_only_cmd(*, report: bool = False, regen_baseline: bool = False, quiet: bool = False) -> None:
    """Enforce the keyword-only-arguments convention across ``pipelex/`` source.

    Args:
        report: If True, print the full inventory grouped by package (no pass/fail gating).
        regen_baseline: If True, rewrite the baseline file with all current violations and exit.
        quiet: If True, output only a single validation line (for use in Make targets).
    """
    console = get_console()

    if not SOURCE_ROOT.exists():
        if quiet:
            console.print("[red]✗ Keyword-only check: FAILED[/red] - pipelex/ source root does not exist")
        else:
            console.print()
            console.print("[red]✗[/red] Source root [cyan]pipelex/[/cyan] does not exist")
            console.print()
        sys.exit(1)

    violations = collect_all_violations(SOURCE_ROOT)

    if regen_baseline:
        write_baseline(BASELINE_PATH, keys=(violation.key for violation in violations))
        if quiet:
            console.print(f"[green]✓ Keyword-only baseline written[/green] ({len(violations)} entries)")
        else:
            console.print()
            console.print(f"[green]✓[/green] Wrote baseline [cyan]{escape(BASELINE_PATH.as_posix())}[/cyan] with {len(violations)} entries")
            console.print()
        return

    if report:
        _print_report(violations)
        return

    baseline = load_baseline(BASELINE_PATH)
    current_keys = {violation.key for violation in violations}
    known, new = partition_violations(violations, baseline=baseline)
    stale_baseline_keys = baseline - current_keys

    if not new:
        if quiet:
            suffix = f" ({len(known)} known-debt)" if known else ""
            console.print(f"[green]✓ Keyword-only check: PASSED[/green]{suffix}")
        else:
            _print_success_panel(known=known, stale_baseline_keys=stale_baseline_keys)
        return

    if quiet:
        console.print(f"[red]✗ Keyword-only check: FAILED[/red] - {len(new)} new violation(s). Run [cyan]make check-keyword-only[/cyan] for details.")
    else:
        _print_failure_panel(new=new, known=known, stale_baseline_keys=stale_baseline_keys)
    sys.exit(1)


def _print_success_panel(*, known: list[Violation], stale_baseline_keys: set[str]) -> None:
    """Verbose success output (no new violations)."""
    console = get_console()
    console.print()
    body = "[green]✓[/green] No new keyword-only violations."
    if known:
        body += f"\n\n[dim]{len(known)} known-debt violation(s) remain in the baseline.[/dim]"
    console.print(
        Panel(
            body,
            title="[bold green]Keyword-only Check: PASSED[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )
    _warn_stale_baseline(stale_baseline_keys)
    console.print()


def _print_failure_panel(*, new: list[Violation], known: list[Violation], stale_baseline_keys: set[str]) -> None:
    """Verbose failure output with a per-violation file:line list."""
    console = get_console()
    console.print()
    console.print(
        Panel(
            f"[red]✗[/red] {len(new)} NEW keyword-only violation(s) found.\n\n"
            "[dim]Non-subject parameters must be keyword-only — place a bare `*` before them, "
            "or add `# kw-only: ignore` on the def line if genuinely justified.[/dim]",
            title="[bold red]Keyword-only Check: FAILED[/bold red]",
            border_style="red",
            padding=(1, 2),
        )
    )
    console.print()
    console.print("[bold]New violations:[/bold]")
    for violation in new:
        console.print(f"  [red]{escape(violation.relative_path)}:{violation.lineno}[/red]  [dim]{escape(violation.qualified_name)}[/dim]")
    if known:
        console.print()
        console.print(f"[dim]{len(known)} known-debt violation(s) tolerated by the baseline.[/dim]")
    _warn_stale_baseline(stale_baseline_keys)
    console.print()


def _warn_stale_baseline(stale_baseline_keys: set[str]) -> None:
    """Warn about baseline entries that are no longer violations so the baseline strictly shrinks."""
    if not stale_baseline_keys:
        return
    console = get_console()
    console.print()
    console.print(
        f"[yellow]⚠[/yellow] {len(stale_baseline_keys)} stale baseline entr(y/ies) no longer violate — run [cyan]--regen-baseline[/cyan] to prune:"
    )
    for key in sorted(stale_baseline_keys):
        console.print(f"  [dim]{escape(key)}[/dim]")
