"""Command recording subject grants — the explicit permissions for positional subject parameters.

The keyword-only convention allows a def's subject to stay positional ONLY under a grant recorded in
``subject_grants.toml`` at the repo root (see ``docs/contribute/keyword-only-arguments.md``). This
command is the sole WRITER of that registry: it validates the target def (it must exist, have a
positional non-literal-typed subject, and same-qualname defs must agree on the subject name), records
the subject's param name automatically, and rewrites the file sorted by key so diffs stay stable.

The registry is READ by the stdlib-only ``keyword_only_guard`` (``tomllib``); writes happen only here,
through ``pipelex.tools.misc.toml_utils`` (tomlkit) — never hand-rolled.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from rich.markup import escape

from pipelex.cli.dev_cli.commands.keyword_only_guard import (
    SOURCE_ROOT,
    SUBJECT_GRANTS_FILE,
    DefInfo,
    SubjectGrant,
    SubjectGrantRegistryError,
    collect_def_infos_in_source,
    load_subject_grants,
    module_qname_for,
)
from pipelex.runtime_hub import get_console
from pipelex.tools.misc.toml_utils import save_toml_to_path


def _fail(message: str) -> None:
    """Print an actionable refusal and exit 1 (the CI-gate idiom: loud, non-zero, no traceback)."""
    console = get_console()
    console.print(f"[red]✗ subject-grant: FAILED[/red] - {escape(message)}")
    sys.exit(1)


def _write_registry(*, grants: dict[str, SubjectGrant], root: Path) -> None:
    """Rewrite the registry sorted by key — stable diffs, trivial merges (the file is machine-written)."""
    data: dict[str, Any] = {"version": 1}
    for key in sorted(grants):
        grant = grants[key]
        data[key] = {"param": grant.param, "rationale": grant.rationale}
    save_toml_to_path(data, path=root / SUBJECT_GRANTS_FILE)


def _validated_subject_param(*, func_key: str) -> str:
    """Validate that ``func_key`` names a grantable def and return its subject param name, or exit 1.

    Refusals: malformed key, out-of-scope or missing file, no def with that qualified name, def exempt
    (carve-out — no grant needed), literal-typed subject (banned outright), no positional subject
    (nothing to grant), or same-qualname defs disagreeing on the subject name (align them first).
    """
    relative_path_str, separator, qualified_name = func_key.partition("::")
    if not separator or not qualified_name or not relative_path_str.endswith(".py"):
        _fail(f'the FUNC key must be "<relative_path>::<qualified_name>" (got: {func_key!r})')
    relative_path = Path(relative_path_str)
    if not relative_path.parts or relative_path.parts[0] != SOURCE_ROOT.name:
        _fail(f"'{relative_path_str}' is not under {SOURCE_ROOT.name}/ — only pipelex/ source is in the guard's scope")
    if not relative_path.is_file():
        _fail(f"source file '{relative_path_str}' does not exist (run from the repo root)")

    def_infos = collect_def_infos_in_source(
        relative_path.read_text(encoding="utf-8"),
        module_qname=module_qname_for(relative_path),
        relative_path=relative_path.as_posix(),
    )
    matching: list[DefInfo] = [def_info for def_info in def_infos if def_info.key == func_key]
    if not matching:
        _fail(f"no def '{qualified_name}' found in {relative_path_str} — check the qualified name (Class.method for methods)")
    if all(def_info.status.is_exempt for def_info in matching):
        _fail(f"def '{qualified_name}' is exempt (dunder / framework carve-out / allowlist / escape hatch) — no grant needed")
    if any(def_info.status.is_literal for def_info in matching):
        _fail(f"def '{qualified_name}' has a bool/int/float subject — literal-typed subjects can never be granted; make it keyword-only instead")
    grantable = [def_info for def_info in matching if def_info.status.is_grantable]
    if not grantable:
        _fail(f"def '{qualified_name}' has no positional subject (already fully keyword-only) — nothing to grant")
    subject_names = {def_info.subject_param for def_info in grantable if def_info.subject_param is not None}
    if len(subject_names) > 1:
        _fail(
            f"defs sharing the qualified name '{qualified_name}' disagree on the subject name "
            f"({', '.join(sorted(subject_names))}) — align them first (one grant covers them all)"
        )
    return subject_names.pop()


def subject_grant_cmd(*, func_key: str | None, rationale: str | None, quiet: bool = False) -> None:
    """Record a subject grant in ``subject_grants.toml``.

    Args:
        func_key: The def to grant, keyed ``<relative_path>::<qualified_name>`` (the guard's key format).
        rationale: The on-the-record review decision — an honest, def-specific sentence.
        quiet: If True, keep the success output to a single line.
    """
    console = get_console()
    if not func_key:
        _fail('a FUNC key is required: subject-grant "<relative_path>::<qualified_name>" --rationale "…"')
        return  # unreachable — _fail exits; keeps the type-checker aware func_key is str below
    if rationale is None or not rationale.strip():
        _fail("a non-empty --rationale is required — it is the on-the-record review decision for this grant")
        return  # unreachable
    subject_param = _validated_subject_param(func_key=func_key)

    try:
        grants = load_subject_grants()
    except SubjectGrantRegistryError as exc:
        _fail(str(exc))
        return  # unreachable
    previous = grants.get(func_key)
    grants[func_key] = SubjectGrant(param=subject_param, rationale=rationale.strip())
    _write_registry(grants=grants, root=Path.cwd())

    action = "updated" if previous is not None else "recorded"
    console.print(f"[green]✓ subject-grant {action}[/green]: [cyan]{escape(func_key)}[/cyan] (param [bold]{escape(subject_param)}[/bold])")
    if not quiet:
        console.print(f"  [dim]rationale:[/dim] {escape(rationale.strip())}")
