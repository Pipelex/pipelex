"""Command to update the Pipelex Gateway models reference files."""

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
from pipelex.service_hub import get_console
from pipelex.system.pipelex_service.exceptions import RemoteConfigUnavailableError, RemoteConfigValidationError

# The reference files live in two places that must stay identical: the repo's
# own .pipelex/ (which `check-gateway-models` verifies) and the packaged kit
# configs (shipped to users via `pipelex init config`). The generator writes
# both copies — the kit-config sync excludes these auto-generated files, so the
# generator is the only thing keeping the packaged copy fresh.
GATEWAY_MODELS_REFERENCE_DIRS: tuple[Path, ...] = (
    Path(".pipelex/inference/backends"),
    Path("pipelex/kit/configs/inference/backends"),
)
GATEWAY_MODELS_HTML_FILENAME = "pipelex_gateway_models.md"
GATEWAY_MODELS_PLAIN_FILENAME = "pipelex_gateway_models_plain.md"


def gateway_models_reference_files() -> list[tuple[Path, Path]]:
    """Return the (html_path, plain_path) reference file pairs to keep in sync."""
    return [
        (reference_dir / GATEWAY_MODELS_HTML_FILENAME, reference_dir / GATEWAY_MODELS_PLAIN_FILENAME)
        for reference_dir in GATEWAY_MODELS_REFERENCE_DIRS
    ]


def _all_references_up_to_date(
    reference_files: list[tuple[Path, Path]],
    *,
    expected_html: str,
    expected_plain: str,
) -> bool:
    """Whether every reference file already matches the expected content (ignoring timestamps)."""
    expected_html_normalized = normalize_for_comparison(expected_html)
    expected_plain_normalized = normalize_for_comparison(expected_plain)
    for html_path, plain_path in reference_files:
        if not (html_path.exists() and plain_path.exists()):
            return False
        try:
            existing_html = html_path.read_text(encoding="utf-8")
            existing_plain = plain_path.read_text(encoding="utf-8")
        except OSError:
            return False  # File disappeared or is unreadable — fall through and rewrite
        if normalize_for_comparison(existing_html) != expected_html_normalized:
            return False
        if normalize_for_comparison(existing_plain) != expected_plain_normalized:
            return False
    return True


def update_gateway_models_cmd(*, quiet: bool = False) -> None:
    """Update the Pipelex Gateway models reference files.

    Fetches the current model specifications from the remote config and
    generates updated Markdown reference files in both the .pipelex/ and the
    packaged kit/configs/ locations.

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
    except RemoteConfigUnavailableError as exc:
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

    reference_files = gateway_models_reference_files()
    all_paths = [path for pair in reference_files for path in pair]
    files_block = "\n".join(f"[dim]  - {path}[/dim]" for path in all_paths)

    # Skip writing if every reference file is already current (ignoring the
    # timestamp line) — avoids noisy diffs in PRs.
    if _all_references_up_to_date(reference_files, expected_html=markdown_content, expected_plain=plain_markdown_content):
        if quiet:
            console.print(f"[green]✓ Gateway models update: UP-TO-DATE[/green] ({model_count} models, no changes)")
        else:
            up_to_date_panel = Panel(
                f"[green]✓[/green] Reference files are already up-to-date (skipped write)\n\n{files_block}\n[dim]Models: {model_count}[/dim]",
                title="[bold green]Gateway Models Update: UP-TO-DATE[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
            console.print(up_to_date_panel)
            console.print()
        return

    # Write both reference files into each reference directory.
    for html_path, plain_path in reference_files:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(markdown_content, encoding="utf-8")
        plain_path.write_text(plain_markdown_content, encoding="utf-8")

    if quiet:
        console.print(f"[green]✓ Gateway models update: PASSED[/green] ({model_count} models)")
    else:
        success_panel = Panel(
            f"[green]✓[/green] Reference files updated successfully!\n\n{files_block}\n[dim]Models: {model_count}[/dim]",
            title="[bold green]Gateway Models Update: PASSED[/bold green]",
            border_style="green",
            padding=(1, 2),
        )
        console.print(success_panel)
        console.print()
