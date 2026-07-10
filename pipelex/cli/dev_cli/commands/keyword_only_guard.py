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

The module also exposes an auto-fix surface (``fix_source`` / ``fix_all_violations``) backing the
``--fix`` flag: it inserts a bare ``*`` as far left as possible (right after ``self``/``cls``) so every
non-``self``/``cls`` parameter becomes keyword-only, for the mechanically fixable violations, and reports
the rest for a manual fix. See ``docs/contribute/keyword-only-arguments.md`` (the Auto-fix section) for the
fixable/unfixable shapes.

Beyond the bare-``*`` rule, the guard enforces the **subject-grant registry**: a def may keep its
subject positional only under an explicitly recorded grant in ``subject_grants.toml`` at the repo
root (one entry per def, keyed ``<relative_path>::<qualified_name>``, recording the subject's
``param`` name and a one-sentence ``rationale``). A positional subject without a grant is a
violation; a grant whose def no longer exists (or whose recorded ``param`` no longer matches) is a
violation too — staleness is symmetric. A subject annotated ``bool``/``int``/``float`` (including
their ``Optional``/union-with-``None`` forms) is banned outright, grant or not: ``f(True)`` call
sites are never acceptable. The registry is READ here (``tomllib``, stdlib); it is only ever
WRITTEN by the full ``pipelex-dev subject-grant`` command (tomlkit, via ``toml_utils``).
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, cast

from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

# --------------------------------------------------------------------------------------
# Configuration / carve-out data
# --------------------------------------------------------------------------------------

#: Source root scanned by the guard (relative to the repo root / cwd).
SOURCE_ROOT = Path("pipelex")

#: Committed registry of granted positional subjects (relative to the repo root / cwd).
SUBJECT_GRANTS_FILE = Path("subject_grants.toml")

#: Subject annotations whose values read as bare literals at call sites (`f(True)`, `f(3)`).
#: A positional subject of these types is a violation no matter what — grants are impossible.
LITERAL_SUBJECT_TYPE_NAMES = frozenset({"bool", "int", "float"})

#: The line breaks ``ast``/CPython counts toward ``node.lineno`` — and ONLY these.
#: ``str.splitlines()`` additionally splits on form-feed, vertical tab, NEL, file/group/record/unit
#: separators and the Unicode line/paragraph separators, so a single such character before a violation
#: would shift every subsequent ``lineno``-based index off by one. The capturing group keeps the
#: separators in the split output so :func:`_split_source_lines` can reconstruct the file byte-for-byte.
_LINE_BREAK_RE = re.compile(r"(\r\n|\r|\n)")

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
#: cannot be made keyword-only — same framework-entrypoint category as Typer/pytest. Written bare
#: (``@pass_context``, ``from jinja2 import pass_context``) or attributed (``@jinja2.pass_context``).
BARE_FRAMEWORK_DECORATOR_NAMES = frozenset({"fixture", "pass_context", "pass_environment", "pass_eval_context"})

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


class ViolationKind(StrEnum):
    """The distinct keyword-only violation kinds — each names its own remedy."""

    MISSING_STAR = "missing-star"
    UNGRANTED_SUBJECT = "ungranted-subject"
    LITERAL_SUBJECT = "literal-subject"
    GRANT_PARAM_MISMATCH = "grant-param-mismatch"
    DEAD_GRANT = "dead-grant"

    @property
    def remedy(self) -> str:
        """One actionable sentence naming how to fix this violation kind."""
        match self:
            case ViolationKind.MISSING_STAR:
                return "place a bare `*` so non-subject parameters are keyword-only, or run `make fko`"
            case ViolationKind.UNGRANTED_SUBJECT:
                return (
                    "run `make fko` to make the subject keyword-only, or keep it positional with "
                    '`make subject-grant FUNC="<path>::<qualname>" RATIONALE="…"`'
                )
            case ViolationKind.LITERAL_SUBJECT:
                return (
                    "a bool/int/float subject reads as a bare literal at call sites — make it keyword-only "
                    "(`make fko`); literal-typed subjects can never be granted"
                )
            case ViolationKind.GRANT_PARAM_MISMATCH:
                return "the recorded grant no longer matches the def's subject — re-run `make subject-grant`, or clean up subject_grants.toml"
            case ViolationKind.DEAD_GRANT:
                return (
                    "no def with a positional subject matches this grant — remove the entry from subject_grants.toml (re-grant after a rename/move)"
                )

    @property
    def is_fixable_by_star_insert(self) -> bool:
        """Whether ``--fix`` may resolve this kind by inserting a bare ``*`` (making every param keyword-only)."""
        match self:
            case ViolationKind.MISSING_STAR | ViolationKind.UNGRANTED_SUBJECT | ViolationKind.LITERAL_SUBJECT:
                return True
            case ViolationKind.GRANT_PARAM_MISMATCH | ViolationKind.DEAD_GRANT:
                return False


class Violation(NamedTuple):
    """A single keyword-only convention violation.

    Attributes:
        relative_path: The source file path relative to the repo root.
        qualified_name: Module-relative dotted path (package.module + class chain + function name).
        lineno: 1-based line of the ``def`` for human display only — never part of the stable key.
            Registry-level violations (``dead-grant``) carry ``0``: there is no def line to point at.
        kind: Which rule was broken — determines the remedy shown.
        detail: Optional human-facing specifics (e.g. the subject param name, or the mismatch description).
    """

    relative_path: str
    qualified_name: str
    lineno: int
    kind: ViolationKind
    detail: str = ""

    @property
    def key(self) -> str:
        """Stable identity key for sorting/dedup: ``<relative_path>::<qualified_function_name>`` (no line number)."""
        return f"{self.relative_path}::{self.qualified_name}"


class SubjectGrant(NamedTuple):
    """A recorded permission for one def to keep its subject parameter positional.

    Attributes:
        param: The subject parameter's name — must keep matching the def's first non-``self``/``cls`` param.
        rationale: The on-the-record review decision (an honest, def-specific sentence).
        seeded: Transitional marker for pre-registry entries awaiting genuine review (Phases 2-4 only).
    """

    param: str
    rationale: str
    seeded: bool = False


class SubjectGrantRegistryError(Exception):
    """The subject-grants registry is missing or malformed — no keyword-only verdict can be produced.

    Defined here rather than in an ``exceptions.py`` module (the house convention) because this module
    must stay importable as a standalone single file for the PostToolUse hook's cold-start budget —
    importing a sibling module would drag in the whole ``pipelex`` package import chain.
    """


class SubjectStatus(StrEnum):
    """How a def stands with respect to the positional-subject rule."""

    EXEMPT = "exempt"  # carve-out / escape hatch / symmetric allowlist — never inspected
    NO_POSITIONAL_SUBJECT = "no-positional-subject"  # fully keyword-only, or no params at all
    LITERAL_SUBJECT = "literal-subject"  # positional subject typed bool/int/float — never grantable
    GRANTABLE_SUBJECT = "grantable-subject"  # positional subject that a grant may cover

    @property
    def is_grantable(self) -> bool:
        match self:
            case SubjectStatus.GRANTABLE_SUBJECT:
                return True
            case SubjectStatus.EXEMPT | SubjectStatus.NO_POSITIONAL_SUBJECT | SubjectStatus.LITERAL_SUBJECT:
                return False

    @property
    def is_literal(self) -> bool:
        match self:
            case SubjectStatus.LITERAL_SUBJECT:
                return True
            case SubjectStatus.EXEMPT | SubjectStatus.NO_POSITIONAL_SUBJECT | SubjectStatus.GRANTABLE_SUBJECT:
                return False

    @property
    def is_exempt(self) -> bool:
        match self:
            case SubjectStatus.EXEMPT:
                return True
            case SubjectStatus.NO_POSITIONAL_SUBJECT | SubjectStatus.LITERAL_SUBJECT | SubjectStatus.GRANTABLE_SUBJECT:
                return False


class DefInfo(NamedTuple):
    """Subject-rule facts about one inspected def — feeds grant freshness, seeding, and the grant command.

    Attributes:
        key: Stable identity key, ``<relative_path>::<qualified_name>`` (same format as ``Violation.key``).
        lineno: 1-based line of the ``def``, for human display.
        status: Where the def stands with respect to the positional-subject rule.
        subject_param: The positional subject's name, or ``None`` when the def has none (or is exempt).
    """

    key: str
    lineno: int
    status: SubjectStatus
    subject_param: str | None


#: The complete set of keys a registry entry may carry (``seeded`` is transitional — Phases 2-4 only).
_GRANT_ALLOWED_KEYS = frozenset({"param", "rationale", "seeded"})


def load_subject_grants(*, root: Path | None = None) -> dict[str, SubjectGrant]:
    """Load and validate the subject-grants registry (``subject_grants.toml`` at the repo root).

    Args:
        root: The repo root; defaults to the current working directory (checks and the hook run from there).

    Returns:
        The grants keyed by ``<relative_path>::<qualified_name>``.

    Raises:
        SubjectGrantRegistryError: When the file is missing or malformed. A missing registry is an explicit
            check error, never a silent empty registry — otherwise every granted subject in the tree would
            suddenly report as ungranted (a mass false-violation).
    """
    path = (root or Path.cwd()) / SUBJECT_GRANTS_FILE
    if not path.is_file():
        msg = f"Subject-grants registry not found at '{path}'. It is committed at the repo root; run the check from there."
        raise SubjectGrantRegistryError(msg)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        msg = f"Subject-grants registry '{path}' is not valid TOML: {exc}"
        raise SubjectGrantRegistryError(msg) from exc
    version = raw.pop("version", None)
    if version != 1:
        msg = f"Subject-grants registry '{path}' must declare `version = 1` (found: {version!r})"
        raise SubjectGrantRegistryError(msg)
    grants: dict[str, SubjectGrant] = {}
    for key, raw_entry in raw.items():
        if not isinstance(raw_entry, dict):
            msg = f"Subject-grants registry entry '{key}' must be a table"
            raise SubjectGrantRegistryError(msg)
        if "::" not in key or not key.partition("::")[0].endswith(".py"):
            msg = f"Subject-grants registry key '{key}' is not of the form '<relative_path>::<qualified_name>'"
            raise SubjectGrantRegistryError(msg)
        entry = cast("dict[str, Any]", raw_entry)
        unknown_keys = set(entry) - _GRANT_ALLOWED_KEYS
        if unknown_keys:
            msg = f"Subject-grants registry entry '{key}' has unknown key(s): {sorted(unknown_keys)}"
            raise SubjectGrantRegistryError(msg)
        param = entry.get("param")
        rationale = entry.get("rationale")
        seeded = entry.get("seeded", False)
        if not isinstance(param, str) or not param:
            msg = f"Subject-grants registry entry '{key}' must record a non-empty string `param`"
            raise SubjectGrantRegistryError(msg)
        if not isinstance(rationale, str) or not rationale.strip():
            msg = f"Subject-grants registry entry '{key}' must record a non-empty `rationale`"
            raise SubjectGrantRegistryError(msg)
        if not isinstance(seeded, bool):
            msg = f"Subject-grants registry entry '{key}': `seeded` must be a boolean"
            raise SubjectGrantRegistryError(msg)
        grants[key] = SubjectGrant(param=param, rationale=rationale, seeded=seeded)
    return grants


# --------------------------------------------------------------------------------------
# Carve-out detection (pure AST, no import resolution)
# --------------------------------------------------------------------------------------


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
    return False


def _has_carveout_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Scan the WHOLE decorator stack for a carve-out match (a framework decorator may sit above a custom one)."""
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


def _is_literal_type_name(annotation: ast.expr) -> bool:
    """Whether an annotation node is a bare ``bool``/``int``/``float`` name."""
    return isinstance(annotation, ast.Name) and annotation.id in LITERAL_SUBJECT_TYPE_NAMES


def _union_members(annotation: ast.expr) -> list[ast.expr] | None:
    """Flatten a ``X | Y`` / ``Optional[X]`` / ``Union[X, Y]`` annotation into its members, or None when not a union form."""
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        left = _union_members(annotation.left) or [annotation.left]
        right = _union_members(annotation.right) or [annotation.right]
        return [*left, *right]
    if isinstance(annotation, ast.Subscript):
        callee = _callee_name(annotation.value)
        if callee == "Optional":
            return [annotation.slice]
        if callee == "Union":
            if isinstance(annotation.slice, ast.Tuple):
                return list(annotation.slice.elts)
            return [annotation.slice]
    return None


def _is_literal_typed_annotation(annotation: ast.expr | None) -> bool:
    """Whether an annotation denotes ``bool``/``int``/``float`` — including Optional/union-with-None forms.

    ``bool | None``, ``Optional[int]``, and ``Union[float, None]`` are all literal-typed: their call-site
    values are still bare literals. A union carrying any non-literal member (``int | str``) is not.
    An absent annotation is not literal-typed — the ban is on provably-literal subjects only.
    """
    if annotation is None:
        return False
    members = _union_members(annotation)
    if members is None:
        return _is_literal_type_name(annotation)
    has_literal = False
    for member in members:
        if isinstance(member, ast.Constant) and member.value is None:
            continue
        if _is_literal_type_name(member) or _is_literal_typed_annotation(member):
            has_literal = True
            continue
        return False
    return has_literal


def _subject_param(node: ast.FunctionDef | ast.AsyncFunctionDef, *, is_method: bool) -> ast.arg | None:
    """The def's subject: its first positional (positional-only or positional-or-keyword) param after ``self``/``cls``."""
    params = [*node.args.posonlyargs, *node.args.args]
    if is_method and params and params[0].arg in {"self", "cls"}:
        params = params[1:]
    return params[0] if params else None


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
    grants: Mapping[str, SubjectGrant],
) -> tuple[Violation | None, DefInfo]:
    """Apply the carve-outs then the rules to a single def; return its (violation-or-None, DefInfo) pair."""
    local_qname = _qualify(node.name, class_stack=class_stack, func_stack=func_stack)
    key = f"{relative_path}::{local_qname}"

    # Carve-outs first — any match => skip entirely (an exempt def neither needs nor keeps a grant alive).
    is_exempt = (
        _is_dunder(node.name)
        or _def_line_has_escape_hatch(node, source_lines=source_lines)
        or _has_carveout_decorator(node)
        or _has_typer_param_annotation(node)
        or (f"{module_qname}.{local_qname}", relative_path) in SYMMETRIC_ALLOWLIST
    )
    if is_exempt:
        return None, DefInfo(key=key, lineno=node.lineno, status=SubjectStatus.EXEMPT, subject_param=None)

    subject = _subject_param(node, is_method=is_method)
    if subject is None:
        return None, DefInfo(key=key, lineno=node.lineno, status=SubjectStatus.NO_POSITIONAL_SUBJECT, subject_param=None)

    is_literal = _is_literal_typed_annotation(subject.annotation)
    status = SubjectStatus.LITERAL_SUBJECT if is_literal else SubjectStatus.GRANTABLE_SUBJECT
    def_info = DefInfo(key=key, lineno=node.lineno, status=status, subject_param=subject.arg)

    # Rule 1 (the bare-`*` rule): a violation once any non-subject positional-or-keyword param remains
    # after dropping self/cls. This dominates the subject rules — the auto-fix makes the def all-keyword.
    if _positional_or_keyword_count(node, is_method=is_method) >= 1:
        violation = Violation(relative_path=relative_path, qualified_name=local_qname, lineno=node.lineno, kind=ViolationKind.MISSING_STAR)
        return violation, def_info

    # Rule 2 (the subject rules): a positional subject is legal only under an explicit grant,
    # and never when literal-typed — `f(True)` call sites are unacceptable no matter what.
    if is_literal:
        violation = Violation(
            relative_path=relative_path,
            qualified_name=local_qname,
            lineno=node.lineno,
            kind=ViolationKind.LITERAL_SUBJECT,
            detail=f"subject '{subject.arg}'",
        )
        return violation, def_info
    grant = grants.get(key)
    if grant is None:
        violation = Violation(
            relative_path=relative_path,
            qualified_name=local_qname,
            lineno=node.lineno,
            kind=ViolationKind.UNGRANTED_SUBJECT,
            detail=f"subject '{subject.arg}'",
        )
        return violation, def_info
    if grant.param != subject.arg:
        violation = Violation(
            relative_path=relative_path,
            qualified_name=local_qname,
            lineno=node.lineno,
            kind=ViolationKind.GRANT_PARAM_MISMATCH,
            detail=f"grant records param '{grant.param}' but the subject is '{subject.arg}'",
        )
        return violation, def_info
    return None, def_info


def _fix_insertion_point(node: ast.FunctionDef | ast.AsyncFunctionDef, *, is_method: bool) -> tuple[int, int] | None:
    """Locate where a bare ``*`` must be inserted to fix a violation, or None if not mechanically fixable.

    The ``*`` is placed as far left as possible — immediately after ``self``/``cls`` (and after any ``/``)
    — so EVERY non-``self``/``cls`` parameter becomes keyword-only, not just the params after the subject:
    ``def f(a, b)`` is fixed to ``def f(*, a, b)`` and ``def m(self, a, b)`` to ``def m(self, *, a, b)``.
    The convention permits the subject to stay positional, but making it keyword-only too is always allowed
    and is preferred here (see ``docs/contribute/keyword-only-arguments.md``).

    Returns the ``(lineno, col_offset)`` of the parameter the bare ``*`` must immediately precede — the
    first positional-or-keyword parameter that is not ``self``/``cls``. The ``col_offset`` is a UTF-8 byte
    offset, matching ``ast`` (see :func:`fix_source` for how it is used).

    Returns None for the signatures a simple bare-``*`` insert cannot fix — these need human judgement:

    - a ``*args`` is present (``node.args.vararg``): a bare ``*`` cannot coexist with ``*args``;
    - a keyword-only section already exists (``node.args.kwonlyargs`` while ``vararg`` is None means a bare
      ``*`` is already in the signature): a second bare ``*`` is a syntax error, so the existing one must be
      moved by hand;
    - two or more positional-only parameters (before a ``/``, excluding a leading ``self``/``cls``) remain:
      a bare ``*`` cannot precede the ``/``, so they stay positional and the single allowed subject is not
      enough to reach compliance.
    """
    if node.args.vararg is not None or node.args.kwonlyargs:
        return None
    args = node.args.args
    # self/cls (when it leads the positional-or-keyword params) stays positional; the `*` goes right after it.
    skip = 1 if (is_method and args and args[0].arg in {"self", "cls"}) else 0
    if skip >= len(args):
        return None  # nothing after self/cls in the positional-or-keyword section to make keyword-only
    # A bare `*` cannot precede a `/`, so positional-only params can't be made keyword-only. After the
    # insert, only the positional-only params (plus a leading self/cls) stay positional; mirror
    # `_positional_or_keyword_count` on that residue — the convention allows exactly one (the subject), so
    # two or more leftover positional-or-keyword params mean a bare `*` can't reach compliance.
    residual_positional = [*node.args.posonlyargs, *args[:skip]]
    if is_method and residual_positional and residual_positional[0].arg in {"self", "cls"}:
        residual_positional = residual_positional[1:]
    if len(residual_positional) > 1:
        return None
    target = args[skip]
    return (target.lineno, target.col_offset)


class _FixRecord(NamedTuple):
    """A violation paired with where to insert the bare ``*`` (or None when it needs a manual fix)."""

    violation: Violation
    insertion: tuple[int, int] | None


class _Collector(ast.NodeVisitor):
    """Walks the module, tracking the enclosing class/function scope to qualify defs."""

    def __init__(
        self,
        *,
        module_qname: str,
        relative_path: str,
        source_lines: list[str],
        grants: Mapping[str, SubjectGrant],
        collect_fixes: bool = False,
    ) -> None:
        self.module_qname = module_qname
        self.relative_path = relative_path
        self.source_lines = source_lines
        self.grants = grants
        self.collect_fixes = collect_fixes
        self.violations: list[Violation] = []
        self.fix_records: list[_FixRecord] = []
        self.def_infos: list[DefInfo] = []
        self._class_stack: tuple[str, ...] = ()
        self._func_stack: tuple[str, ...] = ()
        self._in_class_body: tuple[bool, ...] = ()

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        self._class_stack = (*self._class_stack, node.name)
        self._in_class_body = (*self._in_class_body, True)
        self.generic_visit(node)
        self._class_stack = self._class_stack[:-1]
        self._in_class_body = self._in_class_body[:-1]

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        is_method = bool(self._in_class_body) and self._in_class_body[-1]
        violation, def_info = _evaluate_def(
            node,
            module_qname=self.module_qname,
            relative_path=self.relative_path,
            class_stack=self._class_stack,
            func_stack=self._func_stack,
            is_method=is_method,
            source_lines=self.source_lines,
            grants=self.grants,
        )
        self.def_infos.append(def_info)
        if violation is not None:
            self.violations.append(violation)
            if self.collect_fixes:
                # A bare-`*` insert can only resolve the star-insert-fixable kinds; a grant mismatch
                # needs a registry decision, never a silent signature rewrite.
                insertion = _fix_insertion_point(node, is_method=is_method) if violation.kind.is_fixable_by_star_insert else None
                self.fix_records.append(_FixRecord(violation=violation, insertion=insertion))
        # Descend into the function body; nested defs are NOT methods of the enclosing class.
        self._func_stack = (*self._func_stack, node.name)
        self._in_class_body = (*self._in_class_body, False)
        self.generic_visit(node)
        self._func_stack = self._func_stack[:-1]
        self._in_class_body = self._in_class_body[:-1]

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        self._visit_function(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # pylint: disable=invalid-name  # ast.NodeVisitor dispatch name
        self._visit_function(node)


def _split_source_lines(source: str) -> list[str]:
    """Split ``source`` into content lines indexable by ``ast`` line number (``node.lineno - 1``).

    Unlike ``str.splitlines()``, this splits ONLY on the tokenizer's newline set (see :data:`_LINE_BREAK_RE`),
    so an exotic-whitespace character earlier in the file never shifts a ``lineno``-based index. The content
    lines are the even-indexed elements of the capturing split (odd indices are the separators).
    """
    return _LINE_BREAK_RE.split(source)[::2]


def find_violations_in_source(source: str, *, module_qname: str, relative_path: str, grants: Mapping[str, SubjectGrant]) -> list[Violation]:
    """Find all keyword-only convention violations in a single Python source string.

    Registry-level freshness (dead grants) is NOT checked here — a single source string cannot know
    whether a grant's def exists elsewhere; that is :func:`collect_all_violations`'s job.

    Args:
        source: The Python source text to scan.
        module_qname: The dotted module path used to qualify each def (e.g. ``pipelex.builder.foo``).
        relative_path: The source file path relative to the repo root (used in the violation's sort/identity key).
        grants: The subject-grants registry content (see :func:`load_subject_grants`).

    Returns:
        The violations found, in source order.
    """
    tree = ast.parse(source)
    collector = _Collector(module_qname=module_qname, relative_path=relative_path, source_lines=_split_source_lines(source), grants=grants)
    collector.visit(tree)
    return collector.violations


def collect_def_infos_in_source(source: str, *, module_qname: str, relative_path: str) -> list[DefInfo]:
    """Collect the per-def subject facts for a single source string (feeds the grant command and seeding).

    Args:
        source: The Python source text to scan.
        module_qname: The dotted module path used to qualify each def.
        relative_path: The source file path relative to the repo root (used in each info's key).

    Returns:
        One :class:`DefInfo` per def the walker encounters, in source order.
    """
    tree = ast.parse(source)
    collector = _Collector(module_qname=module_qname, relative_path=relative_path, source_lines=_split_source_lines(source), grants={})
    collector.visit(tree)
    return collector.def_infos


# --------------------------------------------------------------------------------------
# Auto-fix (insert a bare `*` before the first non-self/cls positional-or-keyword param)
# --------------------------------------------------------------------------------------


def _find_fix_records_in_source(source: str, *, module_qname: str, relative_path: str, grants: Mapping[str, SubjectGrant]) -> list[_FixRecord]:
    """Collect a fix record (violation + insertion point) for every violation in a single source string."""
    tree = ast.parse(source)
    collector = _Collector(
        module_qname=module_qname,
        relative_path=relative_path,
        source_lines=_split_source_lines(source),
        grants=grants,
        collect_fixes=True,
    )
    collector.visit(tree)
    return collector.fix_records


def fix_source(
    source: str, *, module_qname: str, relative_path: str, grants: Mapping[str, SubjectGrant]
) -> tuple[str, list[Violation], list[Violation]]:
    """Insert a bare ``*`` for every mechanically-fixable violation in a single source string.

    Returns ``(new_source, fixed, unfixable)``: the rewritten text, the violations that were auto-fixed,
    and the violations that need a manual fix (see :func:`_fix_insertion_point` for which shapes those are).
    If the rewrite somehow fails to re-parse, the original source is returned unchanged and every violation
    is reported as unfixable — a rewrite that breaks the file is never written.

    Args:
        source: The Python source text to fix.
        module_qname: The dotted module path used to qualify each def (e.g. ``pipelex.builder.foo``).
        relative_path: The source file path relative to the repo root (used in each violation's key).
        grants: The subject-grants registry content (an ungranted subject is a fixable violation).
    """
    records = _find_fix_records_in_source(source, module_qname=module_qname, relative_path=relative_path, grants=grants)
    fixable = [(record.violation, record.insertion) for record in records if record.insertion is not None]
    unfixable = [record.violation for record in records if record.insertion is None]
    if not fixable:
        return source, [], unfixable

    # Split keeping separators so the file rebuilds byte-for-byte. Content of `ast` line N is the
    # even-indexed element at `(N - 1) * 2`; odd indices are the separators (see _LINE_BREAK_RE).
    parts = _LINE_BREAK_RE.split(source)
    # Apply bottom-up so an earlier insertion never shifts a not-yet-applied byte offset.
    for lineno, col in sorted((insertion for _, insertion in fixable), reverse=True):
        content_index = (lineno - 1) * 2
        line_bytes = parts[content_index].encode("utf-8")
        parts[content_index] = (line_bytes[:col] + b"*, " + line_bytes[col:]).decode("utf-8")
    new_source = "".join(parts)

    try:
        ast.parse(new_source)
    except SyntaxError:
        return source, [], [record.violation for record in records]
    return new_source, [violation for violation, _ in fixable], unfixable


# --------------------------------------------------------------------------------------
# Filesystem walking
# --------------------------------------------------------------------------------------


def module_qname_for(path: Path) -> str:
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


def find_dead_grants(*, grants: Mapping[str, SubjectGrant], live_subject_keys: set[str]) -> list[Violation]:
    """Report every grant whose key matches no inspected def with a positional subject (staleness is symmetric).

    A grant dies when its def is deleted, renamed, moved, demoted to all-keyword, or newly carved out —
    every one of those must force a deliberate registry decision rather than rot silently.

    Args:
        grants: The subject-grants registry content.
        live_subject_keys: The keys of every inspected def that has a positional subject.
    """
    dead: list[Violation] = []
    for key, grant in grants.items():
        if key in live_subject_keys:
            continue
        relative_path, _, qualified_name = key.partition("::")
        dead.append(
            Violation(
                relative_path=relative_path,
                qualified_name=qualified_name,
                lineno=0,
                kind=ViolationKind.DEAD_GRANT,
                detail=f"granted param '{grant.param}'",
            )
        )
    return dead


def collect_all_violations(root: Path, *, grants: Mapping[str, SubjectGrant]) -> list[Violation]:
    """Scan every source file under ``root`` and return all violations (including dead grants), sorted by key."""
    violations: list[Violation] = []
    live_subject_keys: set[str] = set()
    for path in iter_source_files(root):
        relative_path = path.as_posix()
        module_qname = module_qname_for(path)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        collector = _Collector(module_qname=module_qname, relative_path=relative_path, source_lines=_split_source_lines(source), grants=grants)
        collector.visit(tree)
        violations.extend(collector.violations)
        for def_info in collector.def_infos:
            if def_info.subject_param is not None:
                live_subject_keys.add(def_info.key)
    violations.extend(find_dead_grants(grants=grants, live_subject_keys=live_subject_keys))
    return sorted(violations, key=lambda violation: violation.key)


def collect_all_def_infos(root: Path) -> list[DefInfo]:
    """Collect the per-def subject facts for every source file under ``root`` (feeds seeding and reports)."""
    def_infos: list[DefInfo] = []
    for path in iter_source_files(root):
        source = path.read_text(encoding="utf-8")
        def_infos.extend(collect_def_infos_in_source(source, module_qname=module_qname_for(path), relative_path=path.as_posix()))
    return def_infos


def fix_all_violations(root: Path, *, grants: Mapping[str, SubjectGrant]) -> tuple[list[Violation], list[Violation]]:
    """Rewrite every mechanically-fixable violation under ``root`` in place.

    Returns ``(fixed, unfixable)``, each sorted by key: the violations auto-fixed by inserting a bare
    ``*`` as far left as possible (right after ``self``/``cls``), and those that still need a manual fix.
    Only files whose content actually changed are rewritten. Inserted text stays on the def's original
    line(s); a subsequent ``ruff format`` (the next step in ``make agent-check``) normalizes the layout.
    """
    fixed_all: list[Violation] = []
    unfixable_all: list[Violation] = []
    for path in iter_source_files(root):
        source = path.read_text(encoding="utf-8")
        new_source, fixed, unfixable = fix_source(source, module_qname=module_qname_for(path), relative_path=path.as_posix(), grants=grants)
        if new_source != source:
            path.write_text(new_source, encoding="utf-8")
        fixed_all.extend(fixed)
        unfixable_all.extend(unfixable)
    return sorted(fixed_all, key=lambda violation: violation.key), sorted(unfixable_all, key=lambda violation: violation.key)


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


def collect_violations_for_files(paths: Iterable[Path], *, root: Path | None = None, grants: Mapping[str, SubjectGrant]) -> list[Violation]:
    """Find violations across the given files; out-of-scope, missing, or unparseable files are skipped.

    Results are an exact subset of :func:`collect_all_violations` for the def-level rules:
    ``relative_path`` and ``module_qname`` are computed identically (the carve-out allowlist keys on
    both), so a single-file scan agrees with the full-tree scan for that file. Registry-level freshness
    (dead grants) is full-scan-only — a single file cannot know whether a grant's def exists elsewhere.

    A file that does not parse yet (``SyntaxError``) is skipped rather than reported — a mid-edit file
    is not a keyword-only violation, and the hook must never block on a transient syntax error.

    Args:
        paths: Edited paths, absolute or relative to ``root``.
        root: The repo root; defaults to the current working directory.
        grants: The subject-grants registry content (see :func:`load_subject_grants`).
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
                module_qname=module_qname_for(relative),
                relative_path=relative.as_posix(),
                grants=grants,
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
    try:
        grants = load_subject_grants()
    except SubjectGrantRegistryError as exc:
        print(f"✗ Keyword-only check could not run: {exc}", file=sys.stderr)
        return 2
    violations = collect_violations_for_files([Path(arg) for arg in argv], grants=grants)
    if not violations:
        return 0
    print("✗ Keyword-only violation(s) in edited pipelex source:", file=sys.stderr)
    for violation in violations:
        detail = f"  ({violation.detail})" if violation.detail else ""
        print(f"  {violation.relative_path}:{violation.lineno}  {violation.qualified_name}  [{violation.kind}]{detail}", file=sys.stderr)
    for kind in sorted({violation.kind for violation in violations}):
        print(f"  fix [{kind}]: {kind.remedy}", file=sys.stderr)
    print(
        "A justified one-off may use `# kw-only: ignore` on the def line — see docs/contribute/keyword-only-arguments.md",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
