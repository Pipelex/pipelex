"""Command to verify the MTHDS JSON Schema file is up-to-date."""

from __future__ import annotations

import json
import sys
from difflib import unified_diff
from typing import TYPE_CHECKING

from rich.markup import escape
from rich.panel import Panel

from pipelex.cli.dev_cli.commands.generate_mthds_schema_cmd import MTHDS_SCHEMA_PATH
from pipelex.hub import get_console
from pipelex.language.mthds_schema_generator import generate_mthds_schema

if TYPE_CHECKING:
    from rich.console import Console


def check_mthds_schema_cmd(show_diff: bool = True, *, quiet: bool = False) -> None:
    """Verify that the MTHDS JSON Schema file is up-to-date.

    Regenerates the schema in memory and compares it against the on-disk file.

    Args:
        show_diff: If True, display the differences when found.
        quiet: If True, output only a single validation line (for use in Make targets).
    """
    console = get_console()

    if not quiet:
        console.print()
        console.print("[bold]Checking MTHDS JSON Schema freshness...[/bold]")
        console.print()

    # Check if the schema file exists
    if not MTHDS_SCHEMA_PATH.exists():
        if quiet:
            console.print("[red]✗ MTHDS schema check: FAILED[/red] - Schema file does not exist. Run [cyan]make gms[/cyan] to generate it.")
        else:
            error_panel = Panel(
                f"[red]✗[/red] Schema file does not exist:\n\n[dim]  - {MTHDS_SCHEMA_PATH}[/dim]",
                title="[bold red]MTHDS Schema Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
            console.print("[bold yellow]Recommended Action:[/bold yellow]")
            console.print("  Run: [cyan]make generate-mthds-schema[/cyan] or [cyan]make gms[/cyan]")
            console.print()
        sys.exit(1)

    # Generate expected schema
    try:
        schema = generate_mthds_schema()
    except Exception as exc:  # noqa: BLE001
        # Dev CLI command root: any schema-generation failure is reported as a FAILED status line; exit non-zero.
        if quiet:
            console.print(f"[red]✗ MTHDS schema check: FAILED[/red] - Schema generation error: {escape(str(exc))}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] Failed to generate MTHDS schema\n\n[dim]{escape(str(exc))}[/dim]",
                title="[bold red]MTHDS Schema Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
        sys.exit(1)

    expected_content = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"

    # Read existing content
    try:
        existing_content = MTHDS_SCHEMA_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        if quiet:
            console.print(f"[red]✗ MTHDS schema check: FAILED[/red] - File system error: {escape(str(exc))}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] File system error while reading schema file\n\n[dim]{escape(str(exc))}[/dim]",
                title="[bold red]MTHDS Schema Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
        sys.exit(1)

    # Compare content
    if existing_content == expected_content:
        if quiet:
            console.print("[green]✓ MTHDS schema check: PASSED[/green]")
        else:
            success_panel = Panel(
                f"[green]✓[/green] Schema file is up-to-date!\n\n[dim]{MTHDS_SCHEMA_PATH}[/dim]",
                title="[bold green]MTHDS Schema Check: PASSED[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
            console.print(success_panel)
            console.print()
    else:
        if quiet:
            console.print("[red]✗ MTHDS schema check: FAILED[/red] - Schema file out of date. Run [cyan]make gms[/cyan] to regenerate it.")
        else:
            error_panel = Panel(
                f"[red]✗[/red] Schema file is [bold]OUT OF DATE[/bold]!\n\n"
                f"[dim]The on-disk file does not match the generated schema:\n  - {MTHDS_SCHEMA_PATH}[/dim]",
                title="[bold red]MTHDS Schema Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()

            if show_diff:
                _display_diff(existing=existing_content, expected=expected_content, console=console)

            console.print("[bold yellow]Recommended Action:[/bold yellow]")
            console.print("  Run: [cyan]make generate-mthds-schema[/cyan] or [cyan]make gms[/cyan]")
            console.print()

        sys.exit(1)


def _display_diff(*, existing: str, expected: str, console: Console) -> None:
    """Display a simplified diff between existing and expected content.

    Args:
        existing: Current file content.
        expected: Expected file content.
        console: Rich console for output.
    """
    existing_lines = existing.splitlines(keepends=True)
    expected_lines = expected.splitlines(keepends=True)

    diff = list(
        unified_diff(
            existing_lines,
            expected_lines,
            fromfile="existing (on disk)",
            tofile="expected (generated)",
            lineterm="",
        )
    )

    if diff:
        console.print("[bold]Differences:[/bold]")
        console.print()
        for line in diff[:50]:  # Limit output to first 50 lines
            line = line.rstrip("\n")
            escaped_line = escape(line)
            if line.startswith("+") and not line.startswith("+++"):
                console.print(f"[green]{escaped_line}[/green]")
            elif line.startswith("-") and not line.startswith("---"):
                console.print(f"[red]{escaped_line}[/red]")
            elif line.startswith("@@"):
                console.print(f"[cyan]{escaped_line}[/cyan]")
            else:
                console.print(escaped_line)
        if len(diff) > 50:
            console.print(f"[dim]... and {len(diff) - 50} more lines[/dim]")
        console.print()
