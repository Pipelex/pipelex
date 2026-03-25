"""Command to verify the Pipelex Gateway models reference file is up-to-date."""

from __future__ import annotations

import sys
from difflib import unified_diff
from typing import TYPE_CHECKING

from rich.markup import escape
from rich.panel import Panel

from pipelex.cli.dev_cli.commands.gateway_models_generator import (
    fetch_gateway_model_specs,
    generate_reference_markdown,
    generate_reference_pure_markdown,
    normalize_for_comparison,
)
from pipelex.cli.dev_cli.commands.update_gateway_models_cmd import (
    GATEWAY_MODELS_PLAIN_REFERENCE_PATH,
    GATEWAY_MODELS_REFERENCE_PATH,
)
from pipelex.hub import get_console
from pipelex.system.pipelex_service.exceptions import RemoteConfigFetchError, RemoteConfigValidationError

if TYPE_CHECKING:
    from rich.console import Console


def check_gateway_models_cmd(show_diff: bool = True, quiet: bool = False) -> None:
    """Verify that the Pipelex Gateway models reference files are up-to-date.

    Compares the existing reference files against the current remote config.

    Args:
        show_diff: If True, display the differences when found.
        quiet: If True, output only a single validation line (for use in Make targets).
    """
    console = get_console()

    if not quiet:
        console.print()
        console.print("[bold]Checking Pipelex Gateway models reference files...[/bold]")
        console.print()

    # Check if both reference files exist
    missing_files: list[str] = []
    if not GATEWAY_MODELS_REFERENCE_PATH.exists():
        missing_files.append(str(GATEWAY_MODELS_REFERENCE_PATH))
    if not GATEWAY_MODELS_PLAIN_REFERENCE_PATH.exists():
        missing_files.append(str(GATEWAY_MODELS_PLAIN_REFERENCE_PATH))

    if missing_files:
        if quiet:
            console.print("[red]✗ Gateway models check: FAILED[/red] - Reference file(s) do not exist")
        else:
            files_list = "\n".join(f"  - {path}" for path in missing_files)
            error_panel = Panel(
                f"[red]✗[/red] Reference file(s) do not exist:\n\n[dim]{files_list}[/dim]",
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
            console.print(f"[red]✗ Gateway models check: FAILED[/red] - {escape(str(exc))}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] Failed to fetch remote configuration\n\n[dim]{escape(str(exc))}[/dim]",
                title="[bold red]Gateway Models Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
        sys.exit(1)
    except RemoteConfigValidationError as exc:
        if quiet:
            console.print(f"[red]✗ Gateway models check: FAILED[/red] - {escape(str(exc))}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] Invalid remote configuration\n\n[dim]{escape(str(exc))}[/dim]",
                title="[bold red]Gateway Models Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
        sys.exit(1)

    # Generate expected content for both files
    expected_html_content = generate_reference_markdown(model_specs)
    expected_plain_content = generate_reference_pure_markdown(model_specs)

    # Read existing content for both files
    try:
        existing_html_content = GATEWAY_MODELS_REFERENCE_PATH.read_text(encoding="utf-8")
        existing_plain_content = GATEWAY_MODELS_PLAIN_REFERENCE_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        # Handle race condition where file is deleted after exists() check
        # or other filesystem errors (permissions, etc.)
        if quiet:
            console.print(f"[red]✗ Gateway models check: FAILED[/red] - File system error: {escape(str(exc))}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] File system error while reading reference files\n\n[dim]{escape(str(exc))}[/dim]",
                title="[bold red]Gateway Models Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
        sys.exit(1)

    # Compare content (ignoring timestamp line for comparison)
    html_matches = normalize_for_comparison(existing_html_content) == normalize_for_comparison(expected_html_content)
    plain_matches = normalize_for_comparison(existing_plain_content) == normalize_for_comparison(expected_plain_content)

    if html_matches and plain_matches:
        # No differences found in either file
        if quiet:
            console.print("[green]✓ Gateway models check: PASSED[/green]")
        else:
            success_panel = Panel(
                f"[green]✓[/green] Reference files are up-to-date!\n\n"
                f"[dim]HTML-styled: {GATEWAY_MODELS_REFERENCE_PATH}[/dim]\n"
                f"[dim]Plain text:  {GATEWAY_MODELS_PLAIN_REFERENCE_PATH}[/dim]",
                title="[bold green]Gateway Models Check: PASSED[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
            console.print(success_panel)
            console.print()
    else:
        # Differences found in at least one file
        out_of_date_files: list[str] = []
        if not html_matches:
            out_of_date_files.append(str(GATEWAY_MODELS_REFERENCE_PATH))
        if not plain_matches:
            out_of_date_files.append(str(GATEWAY_MODELS_PLAIN_REFERENCE_PATH))

        if quiet:
            console.print("[red]✗ Gateway models check: FAILED[/red] - Reference file(s) out of date")
        else:
            files_list = "\n".join(f"  - {path}" for path in out_of_date_files)
            error_panel = Panel(
                f"[red]✗[/red] Reference file(s) are [bold]OUT OF DATE[/bold]!\n\n"
                f"[dim]The following files do not match the remote configuration:\n{files_list}[/dim]",
                title="[bold red]Gateway Models Check: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()

            if show_diff:
                if not html_matches:
                    console.print(f"[bold]Differences in {GATEWAY_MODELS_REFERENCE_PATH}:[/bold]")
                    _display_diff(existing_html_content, expected_html_content, console)
                if not plain_matches:
                    console.print(f"[bold]Differences in {GATEWAY_MODELS_PLAIN_REFERENCE_PATH}:[/bold]")
                    _display_diff(existing_plain_content, expected_plain_content, console)

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
