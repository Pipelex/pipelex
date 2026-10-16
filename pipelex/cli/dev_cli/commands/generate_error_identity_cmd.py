"""Command to regenerate the committed ``PipelexError`` wire-identity snapshot and the retired error page redirects."""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel

from pipelex.errors.error_identity_snapshot import iter_error_identity_rows, render_error_identity_snapshot
from pipelex.errors.retired_error_pages import render_retired_error_page_redirects
from pipelex.runtime_hub import get_console

# Repo-relative location of the committed snapshot. It lives under ``tests/data/``
# because the test suite is what gates it — there is no separate ``check-`` command
# and no Make gate to keep in sync.
ERROR_IDENTITY_PATH = Path("tests/data/errors/error_identity.txt")

# Repo-relative location of the documentation's configuration, whose ``redirect_maps`` holds the static
# redirects of the retired per-class error pages, each to the page of its class's code.
MKDOCS_CONFIG_PATH = Path("mkdocs.yml")


def generate_error_identity_cmd(*, output: Path | None = None, quiet: bool = False) -> None:
    """Regenerate the ``(error_type, code declaration)`` snapshot for every ``PipelexError`` subclass.

    It also rewrites the targets of ``mkdocs.yml``'s redirects of the retired per-class error pages, which follow
    each class's code (``pipelex/errors/retired_error_pages.py``), when ``output`` is not given.

    Deliberately does NOT bootstrap Pipelex: a code declaration is a class
    attribute, and the discovery helper imports error modules by filename, so
    the whole rendering is pure. That keeps
    this runnable in any environment, including one with no configured backend.

    Args:
        output: Custom output path. Defaults to :data:`ERROR_IDENTITY_PATH`.
        quiet: If ``True``, emit only a single status line.
    """
    console = get_console()
    output_path = output or ERROR_IDENTITY_PATH

    if not quiet:
        console.print()
        console.print("[bold]Generating the PipelexError wire-identity snapshot...[/bold]")
        console.print()

    content = render_error_identity_snapshot()
    row_count = len(iter_error_identity_rows())

    already_current = output_path.exists() and output_path.read_text(encoding="utf-8") == content
    if not already_current:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
    if output is None:
        mkdocs_text = MKDOCS_CONFIG_PATH.read_text(encoding="utf-8")
        redirected_text = render_retired_error_page_redirects(mkdocs_text=mkdocs_text)
        if redirected_text != mkdocs_text:
            MKDOCS_CONFIG_PATH.write_text(redirected_text, encoding="utf-8")
            already_current = False

    status = "unchanged" if already_current else "written"

    if quiet:
        console.print(f"[green]✓ Error identity snapshot: PASSED[/green] ({status}, {row_count} error classes)")
        return

    success_panel = Panel(
        (f"[green]✓[/green] Error identity snapshot {status}.\n\n[dim]Output: {output_path}[/dim]\n[dim]Error classes: {row_count}[/dim]"),
        title="[bold green]Error Identity Snapshot: PASSED[/bold green]",
        border_style="green",
        padding=(1, 2),
    )
    console.print(success_panel)
    console.print()
