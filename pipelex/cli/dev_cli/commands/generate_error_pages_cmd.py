"""Command to generate one docs page per ``PipelexError`` subclass."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.panel import Panel

from pipelex.errors.error_pages_generator import generate_error_pages
from pipelex.hub import get_console
from pipelex.pipelex import Pipelex

# Default destination directory, aligned with the kebab tail of
# :meth:`PipelexError.type_uri` so each ``<base_uri>/<slug>`` URL maps to a
# real file at ``docs/errors/<slug>.md``.
ERROR_PAGES_DIR = Path("docs/errors")


def generate_error_pages_cmd(output: Path | None = None, quiet: bool = False) -> None:
    """Generate per-class error documentation pages.

    Bootstraps Pipelex so the :class:`pipelex.errors.error_manager.ErrorManager`
    singleton is populated (required by :meth:`PipelexError.type_uri`), walks
    every loaded ``PipelexError`` subclass, and writes one markdown page per
    class. Pages already carrying ``<!-- gstack:authored -->`` are preserved
    so hand-edited reference content is never clobbered.

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
    except Exception:  # noqa: BLE001
        # Dev CLI command root: report any generation failure as FAILED; exit non-zero.
        if quiet:
            console.print("[red]✗ Error pages generation: FAILED[/red]")
        else:
            console.print("[bold red]✗ Failed to generate error pages[/bold red]")
        sys.exit(1)
    finally:
        Pipelex.teardown_if_needed()

    written = len(report.written)
    unchanged = len(report.unchanged)
    preserved = len(report.preserved)

    if quiet:
        console.print(f"[green]✓ Error pages generation: PASSED[/green] ({written} written, {unchanged} unchanged, {preserved} preserved)")
        return

    success_panel = Panel(
        (
            f"[green]✓[/green] Error pages generated.\n\n"
            f"[dim]Output: {output_path}[/dim]\n"
            f"[dim]Total pages: {report.total}[/dim]\n"
            f"[dim]Written: {written} · Unchanged: {unchanged} · Preserved (authored): {preserved}[/dim]"
        ),
        title="[bold green]Error Pages Generation: PASSED[/bold green]",
        border_style="green",
        padding=(1, 2),
    )
    console.print(success_panel)
    console.print()
