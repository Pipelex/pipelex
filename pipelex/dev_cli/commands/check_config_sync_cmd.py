"""Command to verify that .pipelex and pipelex/kit/configs are in sync."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from pipelex.tools.misc.diff import has_diff_dirs, make_diff_dirs_pretty
from pipelex.types import StrEnum


class LeadingConfig(StrEnum):
    """Enum for leading configuration options."""

    KIT = "kit"
    INSTALLED = "installed"


def check_config_sync_cmd(
    show_diff: bool = True,
    leading: LeadingConfig = LeadingConfig.INSTALLED,
) -> None:
    """Verify that .pipelex and pipelex/kit/configs are in sync.

    Args:
        show_diff: If True, display the differences when found
        leading: Which configuration is the leading (left) one in the diff.
                 LeadingConfig.INSTALLED means .pipelex is the reference (default),
                 LeadingConfig.KIT means pipelex/kit/configs is the reference
    """
    console = Console()

    # Define the directories to compare
    pipelex_dir = Path(".pipelex")
    configs_dir = Path("pipelex/kit/configs")

    # Check if both directories exist
    if not pipelex_dir.exists():
        console.print()
        console.print("[red]✗[/red] Directory [cyan].pipelex[/cyan] does not exist")
        console.print()
        sys.exit(1)

    if not configs_dir.exists():
        console.print()
        console.print("[red]✗[/red] Directory [cyan]pipelex/kit/configs[/cyan] does not exist")
        console.print()
        sys.exit(1)

    # Determine directory order based on leading parameter
    match leading:
        case LeadingConfig.INSTALLED:
            left_dir = pipelex_dir
            right_dir = configs_dir
            left_label = ".pipelex"
            right_label = "pipelex/kit/configs"
        case LeadingConfig.KIT:
            left_dir = configs_dir
            right_dir = pipelex_dir
            left_label = "pipelex/kit/configs"
            right_label = ".pipelex"

    # Check for differences
    console.print()
    console.print("[bold]Checking config synchronization...[/bold]")
    console.print(f"  Leading: [cyan]{left_label}[/cyan] ↔ [cyan]{right_label}[/cyan]")
    console.print()

    has_diff = has_diff_dirs(left_dir, right_dir)

    if not has_diff:
        # No differences found
        success_panel = Panel(
            "[green]✓[/green] Directories are in sync!\n\n[dim].pipelex and pipelex/kit/configs have no differences.[/dim]",
            title="[bold green]Config Sync Check: PASSED[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
        console.print(success_panel)
        console.print()
        sys.exit(0)

    # Differences found
    error_panel = Panel(
        "[red]✗[/red] Directories are [bold]NOT[/bold] in sync!\n\n[dim].pipelex and pipelex/kit/configs have differences.[/dim]",
        title="[bold red]Config Sync Check: FAILED[/bold red]",
        border_style="red",
        padding=(1, 2),
    )
    console.print(error_panel)
    console.print()

    if show_diff:
        console.print()
        pretty_diff = make_diff_dirs_pretty(left_dir, right_dir)
        console.print(pretty_diff)
        console.print()

    console.print("[bold yellow]Recommended Actions:[/bold yellow]")
    console.print("  • If [cyan].pipelex[/cyan] is correct, run: [cyan]make config-template[/cyan]")
    console.print("  • If [cyan]pipelex/kit/configs[/cyan] is correct, copy it to [cyan].pipelex[/cyan]")
    console.print()

    sys.exit(1)
