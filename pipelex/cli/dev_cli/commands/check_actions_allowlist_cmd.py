"""Command refusing any GitHub Actions ``uses:`` reference the organization's Actions policy would refuse.

The scan lives in the ``actions_allowlist_guard`` module; this module is the presentation layer wired into the
``pipelex-dev`` Typer app (``make check-actions-allowlist`` / ``make agent-check`` / ``make check`` / CI). The
human-readable specification lives in ``docs/contribute/actions-allowlist.md``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from rich.markup import escape
from rich.panel import Panel

from pipelex.cli.dev_cli.commands.actions_allowlist_exceptions import ActionsAllowlistGuardError
from pipelex.cli.dev_cli.commands.actions_allowlist_guard import (
    ALLOWLIST_FILE,
    REMEDY,
    ActionsAllowlistViolation,
    collect_violations,
)
from pipelex.runtime_hub import get_console


def check_actions_allowlist_cmd(*, quiet: bool = False) -> None:
    """Refuse every workflow action the organization's Actions policy, mirrored in the repository, would refuse.

    Args:
        quiet: If True, keep the success output to a single line (for Make targets / CI). Quiet only trims
            the happy path: a failure still prints every offending reference.
    """
    console = get_console()

    try:
        violations = collect_violations(root=Path())
    except ActionsAllowlistGuardError as exc:
        # An error is always loud: quiet only trims success output, never failures.
        console.print(f"[red]✗ Actions allowlist check: FAILED[/red] - {escape(str(exc))}")
        sys.exit(1)

    if not violations:
        if quiet:
            console.print("[green]✓ Actions allowlist check: PASSED[/green]")
        else:
            console.print()
            console.print(
                Panel(
                    f"[green]✓[/green] Every action the workflows use is one the policy mirrored in [cyan]{escape(ALLOWLIST_FILE.as_posix())}[/cyan] "
                    "allows.",
                    title="[bold green]Actions Allowlist Check: PASSED[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            )
            console.print()
        return

    if quiet:
        console.print(f"[red]✗ Actions allowlist check: FAILED[/red] - {len(violations)} refused action(s):")
    else:
        console.print()
        console.print(
            Panel(
                f"[red]✗[/red] {len(violations)} action(s) the policy mirrored in [cyan]{escape(ALLOWLIST_FILE.as_posix())}[/cyan] refuses.\n\n"
                "[dim]GitHub rejects a whole workflow at startup when one of its actions is not allowed.[/dim]",
                title="[bold red]Actions Allowlist Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
        )
        console.print()
    _print_violations(violations=violations)
    sys.exit(1)


def _print_violations(*, violations: list[ActionsAllowlistViolation]) -> None:
    """Print each refused reference, then the remedy once."""
    console = get_console()
    for violation in violations:
        console.print(
            f"  [red]{escape(violation.relative_path)}:{violation.lineno}[/red]  [cyan]{escape(violation.reference)}[/cyan] "
            f"[yellow]{escape(violation.detail)}[/yellow]"
        )
    console.print(f"[dim]Remedy: {escape(REMEDY)}. See docs/contribute/actions-allowlist.md[/dim]")
