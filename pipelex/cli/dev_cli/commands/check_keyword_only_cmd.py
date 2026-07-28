"""Command enforcing the keyword-only-arguments convention across ``pipelex/`` source.

Non-subject function parameters must be keyword-only so call sites are self-documenting:
``do_thing(retries=3, timeout=30)`` is forced over the opaque ``do_thing(3, 30)``. A positional
subject is legal only under an explicit grant recorded in ``subject_grants.toml`` (see the
``subject-grant`` command), and a ``bool``/``int``/``float`` subject is banned outright. This is
also where the registry's own bookkeeping invariant — entries in sorted key order — is enforced;
the single-file hook path cannot see it, since it is a property of the whole file.

The canonical human-readable specification lives in ``docs/contribute/keyword-only-arguments.md``.
The pure-AST collection logic lives in the stdlib-only ``keyword_only_guard`` module; this module
is the ``rich``/``pipelex.runtime_hub`` presentation layer wired into the ``pipelex-dev`` Typer app
(``make check-keyword-only`` / ``make agent-check`` / CI). The ``pipelex/`` source tree is fully
compliant, so the guard hard-blocks on ANY violation (a bare ``*`` after the subject, a recorded
subject grant, or a ``# kw-only: ignore`` escape hatch with a justification, is required).

The read-only check (``check-keyword-only``, no flag) is the gate; ``--fix`` only mutates and reports.
``--fix`` never exits non-zero on remaining violations, so ``agent-check`` runs it early (fixing before
``ruff format``) without masking the ``pyright``/``mypy`` phase, then runs the read-only check last to
enforce. ``make check`` / CI gate with the read-only check and never mutate.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from rich.markup import escape
from rich.panel import Panel

from pipelex.cli.dev_cli.commands.keyword_only_guard import (
    SOURCE_ROOT,
    SubjectGrantRegistryError,
    Violation,
    collect_all_violations,
    find_unsorted_grants,
    fix_all_violations,
    load_subject_grants,
)
from pipelex.runtime_hub import get_console

if TYPE_CHECKING:
    from pipelex.cli.dev_cli.commands.keyword_only_guard import SubjectGrant

# --------------------------------------------------------------------------------------
# Command entrypoint
# --------------------------------------------------------------------------------------


def _package_of(key_or_path: str) -> str:
    """The top-level package of a ``pipelex/...`` path or ``<path>::<qualname>`` key, for report grouping.

    Files sitting directly under the source root (``pipelex/runtime_hub.py``) group under ``(root)`` rather than
    each filename becoming its own one-off "package" line in the report.
    """
    path = key_or_path.partition("::")[0]
    parts = path.split("/")
    if len(parts) > 2:
        return parts[1]
    return "(root)" if len(parts) == 2 else path


def _print_report(violations: list[Violation], *, grants: dict[str, SubjectGrant]) -> None:
    """Print the full inventory grouped by top-level package, plus the per-package grant counts."""
    console = get_console()
    grouped: dict[str, list[Violation]] = {}
    for violation in violations:
        grouped.setdefault(_package_of(violation.relative_path), []).append(violation)
    console.print()
    console.print("[bold]Keyword-only convention — full inventory[/bold]")
    console.print()
    for package in sorted(grouped):
        package_violations = grouped[package]
        console.print(f"[bold cyan]{escape(package)}[/bold cyan] ([dim]{len(package_violations)}[/dim])")
        for violation in package_violations:
            console.print(
                f"  {escape(violation.relative_path)}:{violation.lineno}  [dim]{escape(violation.qualified_name)}[/dim]"
                f"  [yellow]{escape(violation.kind)}[/yellow]"
            )
        console.print()
    console.print(f"[bold]Total violations:[/bold] {len(violations)}")
    console.print()

    grant_totals: dict[str, int] = {}
    for key in grants:
        package = _package_of(key)
        grant_totals[package] = grant_totals.get(package, 0) + 1
    console.print("[bold]Subject grants by package[/bold]")
    console.print()
    for package in sorted(grant_totals):
        console.print(f"  [bold cyan]{escape(package)}[/bold cyan]  {grant_totals[package]} grant(s)")
    console.print()
    console.print(f"[bold]Grants total:[/bold] {len(grants)}")
    console.print()


def _load_grants_or_exit() -> dict[str, SubjectGrant]:
    """Load the subject-grants registry, or exit 1 with the explicit error (never a silent empty registry)."""
    try:
        return load_subject_grants()
    except SubjectGrantRegistryError as exc:
        console = get_console()
        console.print(f"[red]✗ Keyword-only check: FAILED[/red] - {escape(str(exc))}")
        sys.exit(1)


def _unsorted_grants_or_exit(*, grants: dict[str, SubjectGrant]) -> list[Violation]:
    """Check the registry's file order, or exit 1 with the explicit error (never a silently narrowed scan)."""
    try:
        return find_unsorted_grants(grants=grants)
    except SubjectGrantRegistryError as exc:
        console = get_console()
        console.print(f"[red]✗ Keyword-only check: FAILED[/red] - {escape(str(exc))}")
        sys.exit(1)


def check_keyword_only_cmd(*, report: bool = False, fix: bool = False, quiet: bool = False) -> None:
    """Enforce the keyword-only-arguments convention across ``pipelex/`` source.

    The source tree is fully compliant, so the guard hard-blocks on ANY violation. The only
    sanctioned non-compliant signatures are the explicit carve-outs, the granted positional
    subjects recorded in ``subject_grants.toml``, and the ``# kw-only: ignore`` escape hatch
    (see ``docs/contribute/keyword-only-arguments.md``).

    Args:
        report: If True, print the full inventory grouped by package plus the per-package
            grant counts (no pass/fail gating).
        fix: If True, auto-fix every mechanically-fixable violation by inserting a bare ``*`` as far
            left as possible (right after ``self``/``cls``) so every non-``self``/``cls`` parameter becomes
            keyword-only, then report what was fixed and what still needs a manual fix. Non-gating — it
            reports the unfixable ones but exits 0; the read-only check (run last in ``agent-check`` and
            in ``make check`` / CI) enforces compliance. Takes precedence over ``report``.
        quiet: If True, keep the success output to a single line (for Make targets / CI). Quiet
            only trims the happy path — a failure still prints the full actionable violation list.
    """
    console = get_console()

    if not SOURCE_ROOT.exists():
        # An error is always loud — quiet only trims success output, never failures.
        console.print("[red]✗ Keyword-only check: FAILED[/red] - source root [cyan]pipelex/[/cyan] does not exist")
        sys.exit(1)

    grants = _load_grants_or_exit()

    if fix:
        _run_fix(quiet=quiet, grants=grants)
        return

    # Registry order is a full-scan concern (the single-file hook path cannot see it), so it joins the
    # def-level violations here rather than inside `collect_all_violations`, which stays filesystem-pure.
    violations = sorted(
        [*collect_all_violations(SOURCE_ROOT, grants=grants), *_unsorted_grants_or_exit(grants=grants)],
        key=lambda violation: violation.key,
    )

    if report:
        _print_report(violations, grants=grants)
        return

    if not violations:
        # Success is the only thing quiet trims: one line in quiet mode, a panel otherwise.
        if quiet:
            console.print("[green]✓ Keyword-only check: PASSED[/green]")
        else:
            _print_success_panel()
        return

    # Failure is always actionable: list the offending signatures so no re-run is needed —
    # in quiet mode too, since the Make targets and CI invoke the guard quietly.
    if quiet:
        _print_failure_quiet(violations=violations)
    else:
        _print_failure_panel(violations=violations)
    sys.exit(1)


def _run_fix(*, quiet: bool, grants: dict[str, SubjectGrant]) -> None:
    """Auto-fix path: insert a bare ``*`` for every fixable violation, then report the outcome.

    Non-gating by design: it mutates and reports but never exits non-zero on remaining (unfixable)
    violations. That lets it run early in ``make agent-check`` — fixing before ``ruff format`` without
    aborting the pipeline mid-mutation or masking the ``pyright``/``mypy`` phase. The read-only
    ``check-keyword-only`` gate (run last in ``agent-check``, and in ``make check`` / CI) is what
    enforces compliance and fails on the unfixable ones. A genuine error (e.g. a missing source root)
    still exits non-zero — that is handled by the caller, not here.
    """
    console = get_console()
    fixed, unfixable = fix_all_violations(SOURCE_ROOT, grants=grants)

    if fixed:
        # Files changed — always surface this, even in quiet mode.
        console.print(
            f"[green]✓ Auto-fixed {len(fixed)} keyword-only violation(s)[/green] "
            "(inserted a bare `*` after self/cls so every other parameter is keyword-only):"
        )
        _print_violation_lines(violations=fixed)
        console.print(
            "[dim]Verify with `make agent-test` — the guard can't see framework-positional callers, "
            "so a wrongly keyword-only'd call site only fails at runtime. If a fixed def deserved its "
            "positional subject, revert it and record a grant (`make subject-grant`) instead.[/dim]"
        )

    if unfixable:
        # Reported, not gated here — the read-only `check-keyword-only` (last in agent-check / CI) fails on these.
        console.print(
            f"[red]✗ {len(unfixable)} violation(s) need a manual fix[/red] "
            "(e.g. `*args` present, an existing keyword-only section, two+ positional-only params, or a stale grant):"
        )
        _print_violation_lines(violations=unfixable)
        console.print(
            "[dim]Fix each by hand (its remedy is shown by `make check-keyword-only`), or add `# kw-only: ignore` "
            "on the def line if justified — `make check-keyword-only` (and CI) will fail until then. "
            "See docs/contribute/keyword-only-arguments.md[/dim]"
        )

    if not fixed and not unfixable:
        # Nothing needed fixing — quiet trims this happy path to one line.
        if quiet:
            console.print("[green]✓ Keyword-only auto-fix: nothing to fix[/green]")
        else:
            _print_success_panel()


def _print_success_panel() -> None:
    """Verbose success output (no violations)."""
    console = get_console()
    console.print()
    console.print(
        Panel(
            "[green]✓[/green] No keyword-only violations.",
            title="[bold green]Keyword-only Check: PASSED[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
    )
    console.print()


def _print_failure_panel(*, violations: list[Violation]) -> None:
    """Verbose failure output with a per-violation file:line list grouped by kind."""
    console = get_console()
    console.print()
    console.print(
        Panel(
            f"[red]✗[/red] {len(violations)} keyword-only violation(s) found.\n\n"
            "[dim]Non-subject parameters must be keyword-only, and a positional subject needs a recorded "
            "grant — each violation kind below names its remedy.[/dim]",
            title="[bold red]Keyword-only Check: FAILED[/bold red]",
            border_style="red",
            padding=(1, 2),
        )
    )
    console.print()
    _print_violations_by_kind(violations=violations)


def _print_failure_quiet(*, violations: list[Violation]) -> None:
    """Compact failure output for quiet mode: a status line, then the actionable per-kind violation list."""
    console = get_console()
    console.print(f"[red]✗ Keyword-only check: FAILED[/red] - {len(violations)} violation(s):")
    _print_violations_by_kind(violations=violations)


def _print_violations_by_kind(*, violations: list[Violation]) -> None:
    """Print the violations grouped by kind, each group headed by its remedy."""
    console = get_console()
    grouped: dict[str, list[Violation]] = {}
    for violation in violations:
        grouped.setdefault(violation.kind, []).append(violation)
    for kind_value in sorted(grouped):
        kind_violations = grouped[kind_value]
        kind = kind_violations[0].kind
        console.print(f"[bold]{escape(kind_value)}[/bold] ({len(kind_violations)}) — [dim]{escape(kind.remedy)}[/dim]")
        _print_violation_lines(violations=kind_violations)
    console.print("[dim]See docs/contribute/keyword-only-arguments.md[/dim]")


def _print_violation_lines(*, violations: list[Violation]) -> None:
    """Print one ``file:line  qualified_name`` row per violation."""
    console = get_console()
    for violation in violations:
        detail = f"  [yellow]{escape(violation.detail)}[/yellow]" if violation.detail else ""
        console.print(f"  [red]{escape(violation.relative_path)}:{violation.lineno}[/red]  [dim]{escape(violation.qualified_name)}[/dim]{detail}")
