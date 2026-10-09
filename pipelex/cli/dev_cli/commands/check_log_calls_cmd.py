"""Command holding log calls to the log-call conventions against a baseline that only shrinks.

The AST collection and the baseline logic live in the ``log_call_guard`` module; this module is the presentation
layer wired into the ``pipelex-dev`` Typer app (``make check-log-calls`` / ``make agent-check`` / ``make check`` /
CI). The conventions are in ``docs/tools/logging.md`` and the guard's specification in ``docs/contribute/log-calls.md``.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from rich.markup import escape
from rich.panel import Panel

from pipelex.cli.dev_cli.commands.log_call_guard import (
    BASELINE_FILE,
    BaselineComparison,
    LogCallGuardError,
    LogCallRule,
    OffendingCall,
    StaleEntry,
    collect_offending_calls,
    compare_with_baseline,
    load_baseline,
    package_area_of,
    prune_baseline,
    write_baseline,
)
from pipelex.runtime_hub import get_console

SPEC_DOC = "docs/contribute/log-calls.md"


def check_log_calls_cmd(*, prune: bool = False, report: bool = False, quiet: bool = False) -> None:
    """Refuse a log call that breaks the conventions unless the baseline lists it, and a baseline entry no call matches.

    Args:
        prune: If True, rewrite the baseline without its stale signatures, then check. Pruning never adds an entry,
            so a call the baseline does not list still fails.
        report: If True, print the baseline's calls by package area and exit 0, with no gating.
        quiet: If True, keep the success output to a single line (for Make targets / CI). Quiet only trims the
            happy path: a failure still prints every offending call and every stale entry.
    """
    console = get_console()
    repo_root = Path.cwd()

    try:
        offending = collect_offending_calls(repo_root=repo_root)
        baseline = load_baseline(repo_root=repo_root)
    except LogCallGuardError as exc:
        # An error is always loud: quiet only trims success output, never failures.
        console.print(f"[red]✗ Log-call check: FAILED[/red] - {escape(str(exc))}")
        sys.exit(1)

    if report:
        _print_report(baseline=baseline)
        return

    if prune:
        pruned = prune_baseline(baseline=baseline, offending=offending)
        nb_removed = sum(len(calls) for calls in baseline.values()) - sum(len(calls) for calls in pruned.values())
        if nb_removed:
            write_baseline(baseline=pruned, repo_root=repo_root)
            console.print(f"[green]✓ Removed {nb_removed} stale signature(s) from {escape(BASELINE_FILE.as_posix())}[/green]")
        baseline = pruned

    comparison = compare_with_baseline(offending=offending, baseline=baseline)
    nb_listed = sum(len(calls) for calls in baseline.values())

    if comparison.is_clean:
        if quiet:
            console.print(f"[green]✓ Log-call check: PASSED[/green] ({nb_listed} baselined call(s) left)")
        else:
            console.print()
            console.print(
                Panel(
                    "[green]✓[/green] Every log call follows the conventions or is listed in the baseline, "
                    f"and every listed call still needs its entry.\n\n[dim]{nb_listed} baselined call(s) left to convert.[/dim]",
                    title="[bold green]Log-call Check: PASSED[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            )
            console.print()
        return

    _print_failure(comparison=comparison, quiet=quiet)
    sys.exit(1)


def _print_failure(*, comparison: BaselineComparison, quiet: bool) -> None:
    console = get_console()
    summary = f"{len(comparison.unlisted)} call(s) break the conventions, {len(comparison.stale)} baseline signature(s) are stale"
    if quiet:
        console.print(f"[red]✗ Log-call check: FAILED[/red] - {summary}:")
    else:
        console.print()
        console.print(
            Panel(
                f"[red]✗[/red] {summary}.\n\n"
                "[dim]A message at INFO and above is a literal with its values in `fields=`, and no message holds Rich markup. "
                "The baseline only shrinks.[/dim]",
                title="[bold red]Log-call Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
        )
        console.print()
    if comparison.unlisted:
        _print_unlisted(calls=comparison.unlisted)
    if comparison.stale:
        _print_stale(entries=comparison.stale)
    console.print(f"[dim]See {SPEC_DOC} and the log-call conventions in docs/tools/logging.md[/dim]")


def _print_unlisted(*, calls: list[OffendingCall]) -> None:
    console = get_console()
    console.print("[bold]Calls the baseline does not list[/bold] — convert them; the baseline never grows:")
    rules: set[LogCallRule] = set()
    for call in calls:
        console.print(f"  [red]{escape(call.relative_path)}:{call.lineno}[/red]  [dim]{escape(call.qualified_name)}[/dim]")
        for breach in call.breaches:
            rules.add(breach.rule)
            console.print(f"      [yellow]{escape(breach.rule)}[/yellow]: {escape(breach.detail)}")
    for rule in sorted(rules):
        console.print(f"  [bold]{escape(rule)}[/bold] — [dim]{escape(rule.remedy)}[/dim]")


def _print_stale(*, entries: list[StaleEntry]) -> None:
    console = get_console()
    console.print(
        f"[bold]Stale baseline signatures[/bold] — no call matches them any more (converted, moved or changed): "
        f"remove them from {escape(BASELINE_FILE.as_posix())}, by hand or with `pipelex-dev check-log-calls --prune`:"
    )
    for entry in entries:
        console.print(f"  [red]{escape(entry.key)}[/red]")
        console.print(f"      [dim]{escape(entry.signature)}[/dim]")


def _print_report(*, baseline: dict[str, list[str]]) -> None:
    """Print the baseline's calls by package area, the largest first, for planning the conversion."""
    console = get_console()
    by_area: Counter[str] = Counter()
    for key, calls in baseline.items():
        by_area[package_area_of(key=key)] += len(calls)
    console.print()
    console.print("[bold]Log-call baseline by package area[/bold]")
    console.print()
    for area, nb_calls in by_area.most_common():
        console.print(f"  [bold cyan]{escape(area)}[/bold cyan]  {nb_calls} call(s)")
    console.print()
    console.print(f"[bold]Total baselined calls:[/bold] {by_area.total()}")
    console.print()
