"""Pure-stdlib AST core for the two-hub layering boundary guard.

Pipelex has two hubs. `method_hub` may import `service_hub`; **`service_hub` must never import
`method_hub`**. That single arrow is the whole architecture, and the property it buys is measurable:
importing the inference layer must not load the method interpreter. The canonical human-readable
specification lives in ``docs/contribute/hub-layering.md``.

This module holds the AST collection logic that mechanically enforces two rules:

1. **The layer rule.** A module in the declared low layer (:data:`LOW_LAYER_PACKAGES`) may not import
   ``pipelex.method_hub``. Since `service_hub`'s own closure is what the low layer is, an import
   anywhere in it puts the interpreter back into every inference consumer.
2. **The dead-module rule.** *No* scanned module may reference ``pipelex.hub``. That module was
   deleted rather than kept as an alias for either half, precisely so a stale import fails loudly —
   this rule closes the one hole in that guarantee (see below).

Both rules match **imports and bare string literals**. The string form is not a nicety: a missed
*import* of a deleted module is an immediate ``ImportError``, but a missed *string* is not, and it is
invisible to every import-graph tool and to pyright's module graph. The two forms that actually
occurred in this repo are ``importlib.import_module("pipelex.hub")`` (three of them, hiding a cycle
from every lint) and ``mocker.patch("pipelex.hub.get_console", ...)`` (which broke a whole CLI test
suite with an ``AttributeError`` raised nowhere near a hub). Matching is exact-or-dotted-prefix
against the module path — a docstring or comment that merely *mentions* ``pipelex.method_hub`` in
prose is not a reference and is not flagged. A path assembled at runtime from f-strings or
concatenation is out of reach of any AST scan; nothing in the tree does that today.

Two deliberate carve-outs:

- **``if TYPE_CHECKING:`` blocks are exempt from the layer rule** (but not from the dead-module rule).
  The rule is about what *loads*, and a type-only import loads nothing — deferring a type-only need
  under ``TYPE_CHECKING`` is this repo's sanctioned pattern for it (see the ``pipe_func_executor_registry``
  note in ``docs/contribute/hub-layering.md``). A ``pipelex.hub`` import stays a violation there,
  since the module does not exist in any phase.
- An inline ``# hub-layering: ignore`` comment anywhere on the offending statement suppresses it,
  mirroring the ``# kw-only: ignore`` escape hatch of the sibling keyword-only guard.

The filesystem helpers below are duplicated from ``keyword_only_guard`` on purpose rather than shared:
that module is also invoked *by file path* under a cold-start budget, so it must not import anything
from the ``pipelex`` package chain — extracting a shared helper module would defeat it.

This module depends on **stdlib only** — no ``rich``, ``pipelex.service_hub``, or ``typer``. The
presentation layer wired into the ``pipelex-dev`` Typer app lives in ``check_hub_layering_cmd.py``.
"""

from __future__ import annotations

import ast
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------

#: Source root holding the layered packages (relative to the repo root / cwd).
SOURCE_ROOT = Path("pipelex")

#: Test root. Scanned for the dead-module rule only — `tests.*` is in no declared layer, so the
#: layer rule never applies to it and a test may freely patch `pipelex.method_hub`.
TESTS_ROOT = Path("tests")

#: The roots the full-tree check scans.
SCAN_ROOTS: tuple[Path, ...] = (SOURCE_ROOT, TESTS_ROOT)

#: The declared low layer: packages that must stay importable without loading the method interpreter.
#: `pipelex/core/**` is deliberately absent — five `core/` modules still reach for library lookups, and
#: converting them is design work, not a mechanical move (see the Known inversions section of the doc).
LOW_LAYER_PACKAGES: tuple[str, ...] = (
    "pipelex.cogt",
    "pipelex.plugins",
    "pipelex.reporting",
    "pipelex.system",
    "pipelex.tools",
)

#: The high hub, which no low-layer module may import.
METHOD_HUB_MODULE = "pipelex.method_hub"

#: The single hub that was split and deleted. Every reference to it is dead, in every layer.
#: The marker below is the escape hatch dogfooding itself: this line *declares* the forbidden path,
#: so the guard would otherwise flag its own configuration.
DELETED_HUB_MODULE = "pipelex.hub"  # hub-layering: ignore

#: Inline comment that suppresses a single violation on the statement it sits on.
ESCAPE_HATCH_MARKER = "# hub-layering: ignore"

#: The ``typing.TYPE_CHECKING`` flag name, matched bare (``TYPE_CHECKING``) or attributed (``typing.TYPE_CHECKING``).
TYPE_CHECKING_NAME = "TYPE_CHECKING"


class HubLayeringViolationKind(StrEnum):
    """The distinct hub-layering violation kinds — each names its own remedy."""

    METHOD_HUB_IMPORT = "method-hub-import"
    METHOD_HUB_REFERENCE = "method-hub-reference"
    DEAD_HUB_REFERENCE = "dead-hub-reference"

    @property
    def remedy(self) -> str:
        """One actionable sentence naming how to fix this violation kind."""
        match self:
            case HubLayeringViolationKind.METHOD_HUB_IMPORT:
                return (
                    "a low-layer module may not import `pipelex.method_hub` — take the value as an argument, "
                    "or have the high layer install it downward at boot (the `class_registry_scoping` pattern)"
                )
            case HubLayeringViolationKind.METHOD_HUB_REFERENCE:
                return (
                    "a low-layer module may not name `pipelex.method_hub` in a string either — a dynamic import "
                    "or patch target is the same dependency, just invisible to the import graph"
                )
            case HubLayeringViolationKind.DEAD_HUB_REFERENCE:
                return f"`{DELETED_HUB_MODULE}` no longer exists — point at `pipelex.service_hub` or `pipelex.method_hub`"


class HubLayeringViolation(NamedTuple):
    """One offending import or string literal, located for a report line."""

    relative_path: str
    lineno: int
    kind: HubLayeringViolationKind
    detail: str

    @property
    def key(self) -> str:
        """Stable sort key: file, then line, then kind."""
        return f"{self.relative_path}:{self.lineno:06d}:{self.kind}"


# --------------------------------------------------------------------------------------
# Layer membership and module matching
# --------------------------------------------------------------------------------------


def references_module(*, candidate: str, target: str) -> bool:
    """Whether a dotted candidate names ``target`` or something inside it.

    Exact-or-boundary matching, so ``pipelex.service_hub`` never matches ``pipelex.hub`` and a prose
    sentence mentioning a module is never a reference. The ``:`` form covers ``module:attr`` paths.
    """
    return candidate == target or candidate.startswith((f"{target}.", f"{target}:"))


def is_low_layer(*, module_qname: str) -> bool:
    """Whether a module sits in the declared low layer."""
    return any(module_qname == package or module_qname.startswith(f"{package}.") for package in LOW_LAYER_PACKAGES)


def targets_for(*, module_qname: str) -> frozenset[str]:
    """The forbidden module paths for one module: the dead hub always, plus the high hub in the low layer."""
    if is_low_layer(module_qname=module_qname):
        return frozenset({DELETED_HUB_MODULE, METHOD_HUB_MODULE})
    return frozenset({DELETED_HUB_MODULE})


def _is_type_checking_test(*, test: ast.expr) -> bool:
    """Whether an ``if`` test is the bare ``TYPE_CHECKING`` / ``typing.TYPE_CHECKING`` flag.

    Only the bare forms count: ``if not TYPE_CHECKING:`` guards a *runtime* branch and is not exempt.
    """
    match test:
        case ast.Name(id=name):
            return name == TYPE_CHECKING_NAME
        case ast.Attribute(attr=attr):
            return attr == TYPE_CHECKING_NAME
        case _:
            return False


# --------------------------------------------------------------------------------------
# AST collection
# --------------------------------------------------------------------------------------


class _Collector(ast.NodeVisitor):
    """Walks one module, recording every forbidden import or string reference."""

    def __init__(self, *, relative_path: str, package_qname: str, targets: frozenset[str], source_lines: list[str]) -> None:
        self.relative_path = relative_path
        self.package_qname = package_qname
        self.targets = targets
        self.source_lines = source_lines
        self.violations: list[HubLayeringViolation] = []
        self._type_checking_depth = 0

    def _active_targets(self) -> frozenset[str]:
        """The targets in force here: inside a ``TYPE_CHECKING`` block the layer rule is lifted, the dead-module rule is not."""
        if self._type_checking_depth > 0:
            return self.targets - {METHOD_HUB_MODULE}
        return self.targets

    def _is_suppressed(self, *, lineno: int, end_lineno: int | None) -> bool:
        """Whether the escape-hatch marker sits anywhere on the offending statement's lines."""
        for line_number in range(lineno, (end_lineno or lineno) + 1):
            index = line_number - 1
            if 0 <= index < len(self.source_lines) and ESCAPE_HATCH_MARKER in self.source_lines[index]:
                return True
        return False

    def _matched_target(self, *, candidate: str) -> str | None:
        """The forbidden target this candidate names, if any."""
        for target in sorted(self._active_targets()):
            if references_module(candidate=candidate, target=target):
                return target
        return None

    def _record(self, *, node: ast.AST, target: str, detail: str, import_kind: HubLayeringViolationKind) -> None:
        """Append one violation, unless the statement carries the escape hatch."""
        lineno = getattr(node, "lineno", 0)
        if self._is_suppressed(lineno=lineno, end_lineno=getattr(node, "end_lineno", None)):
            return
        kind = HubLayeringViolationKind.DEAD_HUB_REFERENCE if target == DELETED_HUB_MODULE else import_kind
        self.violations.append(HubLayeringViolation(relative_path=self.relative_path, lineno=lineno, kind=kind, detail=detail))

    def _absolute_module_for(self, *, node: ast.ImportFrom) -> str | None:
        """Resolve an ``ImportFrom``'s module to an absolute dotted path, walking up for relative levels."""
        if node.level == 0:
            return node.module
        parts = self.package_qname.split(".") if self.package_qname else []
        climb = node.level - 1
        if climb > len(parts):
            return None
        base_parts = parts[: len(parts) - climb]
        if node.module:
            base_parts = [*base_parts, *node.module.split(".")]
        return ".".join(base_parts) or None

    @override
    def visit_Import(self, node: ast.Import) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        """``import pipelex.method_hub`` / ``import pipelex.method_hub as hub``."""
        for alias in node.names:
            target = self._matched_target(candidate=alias.name)
            if target is not None:
                self._record(node=node, target=target, detail=f"imports `{alias.name}`", import_kind=HubLayeringViolationKind.METHOD_HUB_IMPORT)
                return

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        """``from pipelex.method_hub import x``, ``from pipelex import method_hub``, and the relative forms."""
        base = self._absolute_module_for(node=node)
        if base is None:
            return
        for candidate in [base, *(f"{base}.{alias.name}" for alias in node.names)]:
            target = self._matched_target(candidate=candidate)
            if target is not None:
                self._record(node=node, target=target, detail=f"imports `{candidate}`", import_kind=HubLayeringViolationKind.METHOD_HUB_IMPORT)
                return

    @override
    def visit_If(self, node: ast.If) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        """Track ``if TYPE_CHECKING:`` depth so its body is exempt from the layer rule."""
        if not _is_type_checking_test(test=node.test):
            self.generic_visit(node)
            return
        self._type_checking_depth += 1
        for statement in node.body:
            self.visit(statement)
        self._type_checking_depth -= 1
        for statement in node.orelse:
            self.visit(statement)

    @override
    def visit_Constant(self, node: ast.Constant) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        """A bare string naming a forbidden module — an ``import_module`` argument, a ``mocker.patch`` target, a config value."""
        value = node.value
        if not isinstance(value, str):
            return
        target = self._matched_target(candidate=value)
        if target is not None:
            self._record(node=node, target=target, detail=f'string literal "{value}"', import_kind=HubLayeringViolationKind.METHOD_HUB_REFERENCE)


# --------------------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------------------


def module_qname_for(*, path: Path) -> str:
    """The dotted module name for a ``.py`` file, relative to the repo root."""
    parts = list(path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def iter_source_files(*, root: Path) -> Iterator[Path]:
    """Yield every ``.py`` file under ``root``, excluding ``__pycache__``."""
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def find_violations_in_source(*, source: str, relative_path: str) -> list[HubLayeringViolation]:
    """Scan one module's source and return its violations.

    Args:
        source: The module's full source text.
        relative_path: Its repo-root-relative posix path — it decides both which layer the module is
            in and how its relative imports resolve, so it must be the real path, not a label.

    Raises:
        SyntaxError: If the source does not parse. Never swallowed: an unparseable module in the
            scanned tree is a real problem, and silently skipping it would create a blind spot.
    """
    path = Path(relative_path)
    collector = _Collector(
        relative_path=relative_path,
        package_qname=".".join(path.parent.parts),
        targets=targets_for(module_qname=module_qname_for(path=path)),
        source_lines=source.splitlines(),
    )
    collector.visit(ast.parse(source))
    return sorted(collector.violations, key=lambda violation: violation.key)


def collect_all_violations(*, roots: Sequence[Path]) -> list[HubLayeringViolation]:
    """Scan every ``.py`` file under each root and return all violations, sorted by location."""
    violations: list[HubLayeringViolation] = []
    for root in roots:
        for path in iter_source_files(root=root):
            violations.extend(find_violations_in_source(source=path.read_text(encoding="utf-8"), relative_path=path.as_posix()))
    return sorted(violations, key=lambda violation: violation.key)
