"""Command to update the Pipelex Gateway models reference file."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.markup import escape
from rich.panel import Panel

from pipelex.cli.dev_cli.commands.gateway_models_generator import (
    fetch_gateway_model_specs,
    generate_reference_markdown,
    generate_reference_pure_markdown,
    normalize_for_comparison,
)
from pipelex.hub import get_console
from pipelex.system.pipelex_service.exceptions import RemoteConfigFetchError, RemoteConfigValidationError

# Path to the reference files
GATEWAY_MODELS_REFERENCE_PATH = Path(".pipelex/inference/backends/pipelex_gateway_models.md")
GATEWAY_MODELS_PLAIN_REFERENCE_PATH = Path(".pipelex/inference/backends/pipelex_gateway_models_plain.md")


def update_gateway_models_cmd(quiet: bool = False) -> None:
    """Update the Pipelex Gateway models reference file.

    Fetches the current model specifications from the remote config and
    generates an updated Markdown reference file.

    Args:
        quiet: If True, output only a single validation line (for use in Make targets).
    """
    console = get_console()

    if not quiet:
        console.print()
        console.print("[bold]Updating Pipelex Gateway models reference...[/bold]")
        console.print()

    # Fetch remote config
    try:
        model_specs = fetch_gateway_model_specs()
    except RemoteConfigFetchError as exc:
        if quiet:
            console.print(f"[red]✗ Gateway models update: FAILED[/red] - {escape(str(exc))}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] Failed to fetch remote configuration\n\n[dim]{escape(str(exc))}[/dim]",
                title="[bold red]Gateway Models Update: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
        sys.exit(1)
    except RemoteConfigValidationError as exc:
        if quiet:
            console.print(f"[red]✗ Gateway models update: FAILED[/red] - {escape(str(exc))}")
        else:
            error_panel = Panel(
                f"[red]✗[/red] Invalid remote configuration\n\n[dim]{escape(str(exc))}[/dim]",
                title="[bold red]Gateway Models Update: FAILED[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
            console.print(error_panel)
            console.print()
        sys.exit(1)

    # Generate markdown content (HTML-styled and pure markdown versions)
    markdown_content = generate_reference_markdown(model_specs)
    plain_markdown_content = generate_reference_pure_markdown(model_specs)

    # Count models for reporting
    model_count = sum(1 for key in model_specs if key != "defaults" and ".rules" not in key and isinstance(model_specs[key], dict))

    # Skip writing if the only change is the timestamp (avoids noisy diffs in PRs)
    if GATEWAY_MODELS_REFERENCE_PATH.exists() and GATEWAY_MODELS_PLAIN_REFERENCE_PATH.exists():
        existing_html = GATEWAY_MODELS_REFERENCE_PATH.read_text(encoding="utf-8")
        existing_plain = GATEWAY_MODELS_PLAIN_REFERENCE_PATH.read_text(encoding="utf-8")
        html_unchanged = normalize_for_comparison(existing_html) == normalize_for_comparison(markdown_content)
        plain_unchanged = normalize_for_comparison(existing_plain) == normalize_for_comparison(plain_markdown_content)
        if html_unchanged and plain_unchanged:
            if quiet:
                console.print(f"[green]✓ Gateway models update: UP-TO-DATE[/green] ({model_count} models, no changes)")
            else:
                up_to_date_panel = Panel(
                    f"[green]✓[/green] Reference files are already up-to-date (skipped write)\n\n"
                    f"[dim]HTML-styled: {GATEWAY_MODELS_REFERENCE_PATH}[/dim]\n"
                    f"[dim]Plain text:  {GATEWAY_MODELS_PLAIN_REFERENCE_PATH}[/dim]\n"
                    f"[dim]Models: {model_count}[/dim]",
                    title="[bold green]Gateway Models Update: UP-TO-DATE[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                )
                console.print(up_to_date_panel)
                console.print()
            return

    # Ensure parent directory exists
    GATEWAY_MODELS_REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Write both reference files
    GATEWAY_MODELS_REFERENCE_PATH.write_text(markdown_content, encoding="utf-8")
    GATEWAY_MODELS_PLAIN_REFERENCE_PATH.write_text(plain_markdown_content, encoding="utf-8")

    if quiet:
        console.print(f"[green]✓ Gateway models update: PASSED[/green] ({model_count} models)")
    else:
        success_panel = Panel(
            f"[green]✓[/green] Reference files updated successfully!\n\n"
            f"[dim]HTML-styled: {GATEWAY_MODELS_REFERENCE_PATH}[/dim]\n"
            f"[dim]Plain text:  {GATEWAY_MODELS_PLAIN_REFERENCE_PATH}[/dim]\n"
            f"[dim]Models: {model_count}[/dim]",
            title="[bold green]Gateway Models Update: PASSED[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
        console.print(success_panel)
        console.print()
