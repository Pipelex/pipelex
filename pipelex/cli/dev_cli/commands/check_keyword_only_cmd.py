"""Command enforcing the keyword-only-arguments convention across ``pipelex/`` source.

Non-subject function parameters must be keyword-only so call sites are self-documenting:
``do_thing(retries=3, timeout=30)`` is forced over the opaque ``do_thing(3, 30)``.

The canonical human-readable specification lives in ``docs/contribute/keyword-only-arguments.md``.
The pure-AST collection logic lives in the stdlib-only ``keyword_only_guard`` module; this module
is the ``rich``/``pipelex.hub`` presentation layer wired into the ``pipelex-dev`` Typer app
(``make check-keyword-only`` / ``make agent-check`` / CI). The ``pipelex/`` source tree is fully
compliant, so the guard hard-blocks on ANY violation (a bare ``*`` after the subject, or a
``# kw-only: ignore`` escape hatch with a justification, is required).

The read-only check (``check-keyword-only``, no flag) is the gate; ``--fix`` only mutates and reports.
``--fix`` never exits non-zero on remaining violations, so ``agent-check`` runs it early (fixing before
``ruff format``) without masking the ``pyright``/``mypy`` phase, then runs the read-only check last to
enforce. ``make check`` / CI gate with the read-only check and never mutate.
"""

from __future__ import annotations

import sys

from rich.markup import escape
from rich.panel import Panel

from pipelex.cli.dev_cli.commands.keyword_only_guard import SOURCE_ROOT, Violation, collect_all_violations, fix_all_violations
from pipelex.hub import get_console

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


def check_keyword_only_cmd(*, report: bool = False, fix: bool = False, quiet: bool = False) -> None:
    """Enforce the keyword-only-arguments convention across ``pipelex/`` source.

    The source tree is fully compliant, so the guard hard-blocks on ANY violation. The only
    sanctioned non-compliant signatures are the explicit carve-outs and the ``# kw-only: ignore``
    escape hatch (see ``docs/contribute/keyword-only-arguments.md``).

    Args:
        report: If True, print the full inventory grouped by package (no pass/fail gating).
        fix: If True, auto-fix every mechanically-fixable violation by inserting a bare ``*`` as far
            left as possible (right after ``self``/``cls``) so every other parameter becomes keyword-only,
            then report what was fixed and what still needs a manual fix. Non-gating — it reports the
            unfixable ones but exits 0; the read-only check (run last in ``agent-check`` and in
            ``make check`` / CI) enforces compliance. Takes precedence over ``report``.
        quiet: If True, keep the success output to a single line (for Make targets / CI). Quiet
            only trims the happy path — a failure still prints the full actionable violation list.
    """
    console = get_console()

    if not SOURCE_ROOT.exists():
        # An error is always loud — quiet only trims success output, never failures.
        console.print("[red]✗ Keyword-only check: FAILED[/red] - source root [cyan]pipelex/[/cyan] does not exist")
        sys.exit(1)

    if fix:
        _run_fix(quiet=quiet)
        return

    violations = collect_all_violations(SOURCE_ROOT)

    if report:
        _print_report(violations)
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


def _run_fix(*, quiet: bool) -> None:
    """Auto-fix path: insert a bare ``*`` for every fixable violation, then report the outcome.

    Non-gating by design: it mutates and reports but never exits non-zero on remaining (unfixable)
    violations. That lets it run early in ``make agent-check`` — fixing before ``ruff format`` without
    aborting the pipeline mid-mutation or masking the ``pyright``/``mypy`` phase. The read-only
    ``check-keyword-only`` gate (run last in ``agent-check``, and in ``make check`` / CI) is what
    enforces compliance and fails on the unfixable ones. A genuine error (e.g. a missing source root)
    still exits non-zero — that is handled by the caller, not here.
    """
    console = get_console()
    fixed, unfixable = fix_all_violations(SOURCE_ROOT)

    if fixed:
        # Files changed — always surface this, even in quiet mode.
        console.print(
            f"[green]✓ Auto-fixed {len(fixed)} keyword-only violation(s)[/green] "
            "(inserted a bare `*` after self/cls so every other parameter is keyword-only):"
        )
        _print_violation_lines(fixed)
        console.print(
            "[dim]Verify with `make agent-test` — the guard can't see framework-positional callers, "
            "so a wrongly keyword-only'd call site only fails at runtime.[/dim]"
        )

    if unfixable:
        # Reported, not gated here — the read-only `check-keyword-only` (last in agent-check / CI) fails on these.
        console.print(
            f"[red]✗ {len(unfixable)} violation(s) need a manual fix[/red] "
            "(e.g. `*args` present, an existing keyword-only section, or two+ positional-only params):"
        )
        _print_violation_lines(unfixable)
        console.print(
            "[dim]Place the bare `*` by hand, or add `# kw-only: ignore` on the def line if justified — "
            "`make check-keyword-only` (and CI) will fail until then. See docs/contribute/keyword-only-arguments.md[/dim]"
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
    """Verbose failure output with a per-violation file:line list."""
    console = get_console()
    console.print()
    console.print(
        Panel(
            f"[red]✗[/red] {len(violations)} keyword-only violation(s) found.\n\n"
            "[dim]Non-subject parameters must be keyword-only — place a bare `*` before them, "
            "or add `# kw-only: ignore` on the def line if genuinely justified.[/dim]",
            title="[bold red]Keyword-only Check: FAILED[/bold red]",
            border_style="red",
            padding=(1, 2),
        )
    )
    console.print()
    console.print("[bold]Violations:[/bold]")
    _print_violation_lines(violations)
    console.print()


def _print_failure_quiet(*, violations: list[Violation]) -> None:
    """Compact failure output for quiet mode: a status line, the actionable file:line list, one remedy hint."""
    console = get_console()
    console.print(f"[red]✗ Keyword-only check: FAILED[/red] - {len(violations)} violation(s):")
    _print_violation_lines(violations)
    console.print(
        "[dim]Place a bare `*` so non-subject parameters are keyword-only (or run `make fix-keyword-only`), "
        "or add `# kw-only: ignore` if justified — see docs/contribute/keyword-only-arguments.md[/dim]"
    )


def _print_violation_lines(violations: list[Violation]) -> None:
    """Print one ``file:line  qualified_name`` row per violation."""
    console = get_console()
    for violation in violations:
        console.print(f"  [red]{escape(violation.relative_path)}:{violation.lineno}[/red]  [dim]{escape(violation.qualified_name)}[/dim]")
