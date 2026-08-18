"""Command to verify that .pipelex and pipelex/kit/configs are in sync."""

from __future__ import annotations

import sys
from enum import StrEnum
from pathlib import Path

from rich.markup import escape
from rich.panel import Panel

from pipelex.cli.dev_cli.config_sync_exclusions import CONFIG_SYNC_EXCLUDED_FILES, CONFIG_SYNC_EXCLUDED_PATTERNS
from pipelex.kit.paths import GIT_IGNORED_CONFIG_DIRS
from pipelex.runtime_hub import get_console
from pipelex.tools.misc.diff import has_diff_dirs, make_diff_dirs_pretty


class LeadingConfig(StrEnum):
    """Enum for leading configuration options."""

    KIT = "kit"
    INSTALLED = "installed"


def check_config_sync_cmd(
    *,
    show_diff: bool = True,
    leading: LeadingConfig = LeadingConfig.INSTALLED,
    quiet: bool = False,
) -> None:
    """Verify that .pipelex and pipelex/kit/configs are in sync.

    Args:
        show_diff: If True, display the differences when found
        leading: Which configuration is the leading (left) one in the diff.
                 LeadingConfig.INSTALLED means .pipelex is the reference (default),
                 LeadingConfig.KIT means pipelex/kit/configs is the reference
        quiet: If True, output only a single validation line (for use in Make targets)
    """
    console = get_console()

    # Define the directories to compare
    pipelex_dir = Path(".pipelex")
    configs_dir = Path("pipelex/kit/configs")

    # Check if both directories exist
    if not pipelex_dir.exists():
        if quiet:
            console.print("[red]✗ Config sync check: FAILED[/red] - .pipelex does not exist")
        else:
            console.print()
            console.print("[red]✗[/red] Directory [cyan].pipelex[/cyan] does not exist")
            console.print()
        sys.exit(1)

    if not configs_dir.exists():
        if quiet:
            console.print("[red]✗ Config sync check: FAILED[/red] - pipelex/kit/configs does not exist")
        else:
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

    # Check for differences (excluding files and directories that intentionally differ)
    try:
        has_diff = has_diff_dirs(
            dir1=left_dir,
            dir2=right_dir,
            exclude_files=CONFIG_SYNC_EXCLUDED_FILES,
            exclude_dirs=GIT_IGNORED_CONFIG_DIRS,
            exclude_patterns=CONFIG_SYNC_EXCLUDED_PATTERNS,
        )
    except OSError as exc:
        # Handle race condition where directories are deleted/modified after existence checks
        if quiet:
            console.print(f"[red]✗ Config sync check: FAILED[/red] - File system error: {escape(str(exc))}")
        else:
            console.print()
            console.print(f"[red]✗[/red] File system error while comparing directories: {escape(str(exc))}")
            console.print()
        sys.exit(1)

    if not has_diff:
        # No differences found
        if quiet:
            console.print("[green]✓ Config sync check: PASSED[/green]")
        else:
            console.print()
            console.print("[bold]Checking config synchronization...[/bold]")
            console.print(f"  Leading: [cyan]{left_label}[/cyan] ↔ [cyan]{right_label}[/cyan]")
            console.print()
            success_panel = Panel(
                "[green]✓[/green] Directories are in sync!\n\n[dim].pipelex and pipelex/kit/configs have no differences.[/dim]",
                title="[bold green]Config Sync Check: PASSED[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
            console.print(success_panel)
            console.print()
    else:
        console.print()
        console.print("[bold]Checking config synchronization...[/bold]")
        console.print(f"  Leading: [cyan]{left_label}[/cyan] ↔ [cyan]{right_label}[/cyan]")
        console.print()
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
            pretty_diff = make_diff_dirs_pretty(
                dir1=left_dir,
                dir2=right_dir,
                exclude_files=CONFIG_SYNC_EXCLUDED_FILES,
                exclude_dirs=GIT_IGNORED_CONFIG_DIRS,
                exclude_patterns=CONFIG_SYNC_EXCLUDED_PATTERNS,
            )
            console.print(pretty_diff)
            console.print()

        console.print("[bold yellow]Recommended Actions:[/bold yellow]")
        console.print("  • If [cyan].pipelex[/cyan] is correct, run: [cyan]make up-kit-configs[/cyan] or simply [cyan]make ukc[/cyan]")
        console.print("  • If [cyan]pipelex/kit/configs[/cyan] is correct, copy it to [cyan].pipelex[/cyan]")
        console.print()

        sys.exit(1)
