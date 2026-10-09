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
    BaselineGrowth,
    LogCallGuardError,
    LogCallRule,
    OffendingCall,
    StaleEntry,
    collect_offending_calls,
    compare_with_baseline,
    compare_with_trusted_baseline,
    load_baseline,
    load_trusted_baseline,
    package_area_of,
    prune_baseline,
    resolve_merge_base,
    write_baseline,
)
from pipelex.runtime_hub import get_console

SPEC_DOC = "docs/contribute/log-calls.md"


def check_log_calls_cmd(
    *,
    prune: bool = False,
    report: bool = False,
    quiet: bool = False,
    against: str | None = None,
    against_merge_base: str | None = None,
) -> None:
    """Refuse a log call that breaks the conventions unless the baseline lists it, a baseline entry no call matches, and a baseline that grew.

    Args:
        prune: If True, rewrite the baseline without its stale signatures, then check. Pruning never adds an entry,
            so a call the baseline does not list still fails.
        report: If True, print the baseline's calls by package area and exit 0, with no gating.
        quiet: If True, keep the success output to a single line (for Make targets / CI). Quiet only trims the
            happy path: a failure still prints every offending call and every stale entry.
        against: A trusted revision whose committed baseline the working one may only shrink from: a signature it
            lists more times than that revision does fails. A revision that does not resolve is an error.
        against_merge_base: A ref whose merge base with ``HEAD`` is the trusted revision; when that merge base does
            not resolve, the comparison is skipped and the output says so.
    """
    console = get_console()
    repo_root = Path.cwd()

    try:
        offending = collect_offending_calls(repo_root=repo_root)
        baseline = load_baseline(repo_root=repo_root)
    except LogCallGuardError as exc:
        # An error is always loud: quiet only trims success output, never failures.
        _print_error(message=str(exc))
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

    try:
        trusted_ref, growth = _shrink_comparison(repo_root=repo_root, baseline=baseline, against=against, against_merge_base=against_merge_base)
    except LogCallGuardError as exc:
        _print_error(message=str(exc))
        sys.exit(1)

    if comparison.is_clean and not growth:
        shrink_note = f", none added since {escape(trusted_ref)}" if trusted_ref is not None else ""
        if quiet:
            console.print(f"[green]✓ Log-call check: PASSED[/green] ({nb_listed} baselined call(s) left{shrink_note})")
        else:
            console.print()
            console.print(
                Panel(
                    "[green]✓[/green] Every log call follows the conventions or is listed in the baseline, "
                    f"and every listed call still needs its entry.\n\n[dim]{nb_listed} baselined call(s) left to convert{shrink_note}.[/dim]",
                    title="[bold green]Log-call Check: PASSED[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            )
            console.print()
        return

    _print_failure(comparison=comparison, growth=growth, trusted_ref=trusted_ref, quiet=quiet)
    sys.exit(1)


def _shrink_comparison(
    *,
    repo_root: Path,
    baseline: dict[str, list[str]],
    against: str | None,
    against_merge_base: str | None,
) -> tuple[str | None, list[BaselineGrowth]]:
    """The trusted revision the baseline was compared with, and what it grew by since; ``None`` and nothing when there was none.

    Says plainly, whatever the verbosity, why a comparison that was asked for did not run.

    Raises:
        LogCallGuardError: When both options are given, or the trusted revision cannot be read.
    """
    console = get_console()
    trusted_commit: str
    trusted_label: str
    if against is not None and against_merge_base is not None:
        msg = "Give `--against` or `--against-merge-base`, not both"
        raise LogCallGuardError(msg)
    if against is not None:
        trusted_commit = against
        trusted_label = f"'{against}'"
    elif against_merge_base is not None:
        merge_base = resolve_merge_base(repo_root=repo_root, ref=against_merge_base)
        if merge_base is None:
            console.print(
                f"[yellow]! Log-call baseline not compared:[/yellow] no merge base of HEAD and '{escape(against_merge_base)}' resolves "
                f"(fetch '{escape(against_merge_base)}' to compare), so nothing here refuses an entry added to the baseline."
            )
            return None, []
        trusted_commit = merge_base
        trusted_label = f"the merge base with {against_merge_base} ({merge_base[:12]})"
    else:
        return None, []
    trusted = load_trusted_baseline(repo_root=repo_root, ref=trusted_commit)
    if trusted is None:
        console.print(
            f"[yellow]! Log-call baseline not compared:[/yellow] the log-call guard does not exist at {escape(trusted_label)}, "
            "so there is no baseline to hold this one to; the comparison applies from the change that introduces it."
        )
        return None, []
    return trusted_label, compare_with_trusted_baseline(baseline=baseline, trusted=trusted)


def _print_error(*, message: str) -> None:
    get_console().print(f"[red]✗ Log-call check: FAILED[/red] - {escape(message)}")


def _print_failure(*, comparison: BaselineComparison, growth: list[BaselineGrowth], trusted_ref: str | None, quiet: bool) -> None:
    console = get_console()
    summary = f"{len(comparison.unlisted)} call(s) break the conventions, {len(comparison.stale)} baseline signature(s) are stale"
    if trusted_ref is not None:
        summary += f", {len(growth)} baseline signature(s) were added since {trusted_ref}"
    if quiet:
        console.print(f"[red]✗ Log-call check: FAILED[/red] - {escape(summary)}:")
    else:
        console.print()
        console.print(
            Panel(
                f"[red]✗[/red] {escape(summary)}.\n\n"
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
    if growth and trusted_ref is not None:
        _print_growth(growth=growth, trusted_ref=trusted_ref)
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


def _print_growth(*, growth: list[BaselineGrowth], trusted_ref: str) -> None:
    console = get_console()
    console.print(
        f"[bold]Baseline signatures added since {escape(trusted_ref)}[/bold] — the baseline only shrinks: "
        "remove these entries and convert the calls they would exempt:"
    )
    for entry in growth:
        console.print(f"  [red]{escape(entry.key)}[/red]  [dim]listed {entry.working_count} time(s), {entry.trusted_count} at the base[/dim]")
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
