"""Command enforcing that no module outside ``pipelex/cli/`` imports Rich at module level, or reaches it through a CLI module.

Rich is the ``cli`` extra, and a server installs pipelex without it. The AST collection lives in the
``rich_import_guard`` module; this module is the presentation layer wired into the
``pipelex-dev`` Typer app (``make check-rich-imports`` / ``make agent-check`` / ``make check`` / CI). The
tree is compliant, so the guard hard-blocks on any violation. The human-readable specification lives in
``docs/contribute/rich-imports.md``.
"""

from __future__ import annotations

import sys

from rich.markup import escape
from rich.panel import Panel

from pipelex.cli.dev_cli.commands.rich_import_guard import (
    CLI_PACKAGE_PREFIX,
    REMEDY,
    SOURCE_ROOT,
    RichImportViolation,
    collect_violations,
)
from pipelex.runtime_hub import get_console


def check_rich_imports_cmd(*, quiet: bool = False) -> None:
    """Refuse a module-level Rich import, direct or through a CLI module, anywhere outside the CLI package.

    Args:
        quiet: If True, keep the success output to a single line (for Make targets / CI). Quiet only
            trims the happy path: a failure still prints every offending import.
    """
    console = get_console()

    if not SOURCE_ROOT.exists():
        # An error is always loud: quiet only trims success output, never failures.
        console.print(f"[red]✗ Rich import check: FAILED[/red] - scan root [cyan]{escape(SOURCE_ROOT.as_posix())}/[/cyan] does not exist")
        sys.exit(1)

    violations = collect_violations(root=SOURCE_ROOT)

    if not violations:
        if quiet:
            console.print("[green]✓ Rich import check: PASSED[/green]")
        else:
            console.print()
            console.print(
                Panel(
                    f"[green]✓[/green] No module outside [cyan]{escape(CLI_PACKAGE_PREFIX)}[/cyan] imports Rich at module level "
                    "or reaches it through a CLI module.",
                    title="[bold green]Rich Import Check: PASSED[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
            )
            console.print()
        return

    if quiet:
        console.print(f"[red]✗ Rich import check: FAILED[/red] - {len(violations)} violation(s):")
    else:
        console.print()
        console.print(
            Panel(
                f"[red]✗[/red] {len(violations)} module-level Rich import(s) or reach(es) outside [cyan]{escape(CLI_PACKAGE_PREFIX)}[/cyan].\n\n"
                "[dim]Rich is the `cli` extra: a server installs pipelex without it.[/dim]",
                title="[bold red]Rich Import Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
        )
        console.print()
    _print_violations(violations=violations)
    sys.exit(1)


def _print_violations(*, violations: list[RichImportViolation]) -> None:
    """Print each offending import, then the remedy once."""
    console = get_console()
    for violation in violations:
        console.print(f"  [red]{escape(violation.relative_path)}:{violation.lineno}[/red]  [yellow]{escape(violation.detail)}[/yellow]")
    console.print(f"[dim]Remedy: {escape(REMEDY)}. See docs/contribute/rich-imports.md[/dim]")
