"""Command to verify the Pipelex Gateway models reference file is up-to-date."""

from __future__ import annotations

import sys
from difflib import unified_diff
from typing import TYPE_CHECKING

from rich.panel import Panel

from pipelex.cli.dev_cli.commands.gateway_models_generator import (
    fetch_gateway_model_specs,
    generate_reference_markdown,
)
from pipelex.cli.dev_cli.commands.update_gateway_models_cmd import GATEWAY_MODELS_REFERENCE_PATH
from pipelex.hub import get_console
from pipelex.system.pipelex_service.exceptions import RemoteConfigFetchError, RemoteConfigValidationError

if TYPE_CHECKING:
    from rich.console import Console


def check_gateway_models_cmd(show_diff: bool = True, quiet: bool = False) -> None:
    """Verify that the Pipelex Gateway models reference file is up-to-date.

    Compares the existing reference file against the current remote config.

    Args:
        show_diff: If True, display the differences when found.
        quiet: If True, output only a single validation line (for use in Make targets).
    """
    console = get_console()

    if not quiet:
        console.print()
        console.print("[bold]Checking Pipelex Gateway models reference...[/bold]")
        console.print()

    # Check if reference file exists
    if not GATEWAY_MODELS_REFERENCE_PATH.exists():
        if quiet:
            console.print("[red]✗ Gateway models check: FAILED[/red] - Reference file does not exist")
        else:
            error_panel = Panel(
                f"[red]✗[/red] Reference file does not exist\n\n[dim]{GATEWAY_MODELS_REFERENCE_PATH}[/dim]",
                title="[bold red]Gateway Models Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
            console.print("[bold yellow]Recommended Action:[/bold yellow]")
            console.print("  Run: [cyan]make update-gateway-models[/cyan] or [cyan]make ugm[/cyan]")
            console.print()
        sys.exit(1)

    # Fetch remote config
    try:
        model_specs = fetch_gateway_model_specs()
    except RemoteConfigFetchError as exc:
        if quiet:
            console.print(f"[red]✗ Gateway models check: FAILED[/red] - {exc}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] Failed to fetch remote configuration\n\n[dim]{exc}[/dim]",
                title="[bold red]Gateway Models Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
        sys.exit(1)
    except RemoteConfigValidationError as exc:
        if quiet:
            console.print(f"[red]✗ Gateway models check: FAILED[/red] - {exc}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] Invalid remote configuration\n\n[dim]{exc}[/dim]",
                title="[bold red]Gateway Models Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
        sys.exit(1)

    # Generate expected content
    expected_content = generate_reference_markdown(model_specs)

    # Read existing content
    existing_content = GATEWAY_MODELS_REFERENCE_PATH.read_text(encoding="utf-8")

    # Compare content (ignoring timestamp line for comparison)
    def normalize_for_comparison(content: str) -> str:
        """Remove timestamp line for comparison since it changes every generation."""
        lines = content.split("\n")
        return "\n".join(line for line in lines if not line.startswith("> Last updated:"))

    existing_normalized = normalize_for_comparison(existing_content)
    expected_normalized = normalize_for_comparison(expected_content)

    if existing_normalized == expected_normalized:
        # No differences found
        if quiet:
            console.print("[green]✓ Gateway models check: PASSED[/green]")
        else:
            success_panel = Panel(
                f"[green]✓[/green] Reference file is up-to-date!\n\n[dim]File: {GATEWAY_MODELS_REFERENCE_PATH}[/dim]",
                title="[bold green]Gateway Models Check: PASSED[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
            console.print(success_panel)
            console.print()
    else:
        # Differences found
        if quiet:
            console.print("[red]✗ Gateway models check: FAILED[/red] - Reference file is out of date")
        else:
            error_panel = Panel(
                "[red]✗[/red] Reference file is [bold]OUT OF DATE[/bold]!\n\n"
                f"[dim]The models in {GATEWAY_MODELS_REFERENCE_PATH} do not match the remote configuration.[/dim]",
                title="[bold red]Gateway Models Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()

            if show_diff:
                _display_diff(existing_content, expected_content, console)

            console.print("[bold yellow]Recommended Action:[/bold yellow]")
            console.print("  Run: [cyan]make update-gateway-models[/cyan] or [cyan]make ugm[/cyan]")
            console.print()

        sys.exit(1)


def _display_diff(existing: str, expected: str, console: Console) -> None:
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
            tofile="expected (from remote)",
            lineterm="",
        )
    )

    if diff:
        console.print("[bold]Differences:[/bold]")
        console.print()
        for line in diff[:50]:  # Limit output to first 50 lines
            line = line.rstrip("\n")
            if line.startswith("+") and not line.startswith("+++"):
                console.print(f"[green]{line}[/green]")
            elif line.startswith("-") and not line.startswith("---"):
                console.print(f"[red]{line}[/red]")
            elif line.startswith("@@"):
                console.print(f"[cyan]{line}[/cyan]")
            else:
                console.print(line)
        if len(diff) > 50:
            console.print(f"[dim]... and {len(diff) - 50} more lines[/dim]")
        console.print()
