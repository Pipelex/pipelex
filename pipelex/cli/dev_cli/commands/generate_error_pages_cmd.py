"""Command to generate one docs page per ``PipelexError`` subclass."""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel

from pipelex.errors.error_pages_generator import generate_error_pages
from pipelex.hub import get_console
from pipelex.pipelex import Pipelex

ERROR_PAGES_DIR = Path("docs/errors")


def generate_error_pages_cmd(output: Path | None = None, quiet: bool = False) -> None:
    """Generate per-class error documentation pages.

    Bootstraps Pipelex so every ``PipelexError`` subclass is imported and thus
    discoverable, walks them all, and writes one markdown page per class. Pages
    already carrying ``<!-- gstack:authored -->`` are preserved so hand-edited
    reference content is never clobbered.

    Args:
        output: Custom output directory. Defaults to ``docs/errors/``.
        quiet: If ``True``, emit only a single status line.
    """
    console = get_console()
    output_path = output or ERROR_PAGES_DIR

    if not quiet:
        console.print()
        console.print("[bold]Generating per-class error documentation pages...[/bold]")
        console.print()

    Pipelex.make()
    try:
        report = generate_error_pages(output_dir=output_path)
    finally:
        Pipelex.teardown_if_needed()

    written = len(report.written)
    unchanged = len(report.unchanged)
    preserved = len(report.preserved)
    removed = len(report.removed)

    if quiet:
        console.print(
            f"[green]✓ Error pages generation: PASSED[/green] ({written} written, {unchanged} unchanged, {preserved} preserved, {removed} removed)"
        )
        return

    success_panel = Panel(
        (
            f"[green]✓[/green] Error pages generated.\n\n"
            f"[dim]Output: {output_path}[/dim]\n"
            f"[dim]Total pages: {report.total}[/dim]\n"
            f"[dim]Written: {written} · Unchanged: {unchanged} · Preserved (authored): {preserved} · Removed: {removed}[/dim]"
        ),
        title="[bold green]Error Pages Generation: PASSED[/bold green]",
        border_style="green",
        padding=(1, 2),
    )
    console.print(success_panel)
    console.print()
