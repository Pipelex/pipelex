"""The commands of Pipelex's error registry: generate its derived files, check them, and write the type URI redirects."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer

from pipelex.cli.dev_cli.commands.error_registry.registry_outputs import (
    check_error_registry,
    render_outputs,
    source_errors,
    summary_line,
    write_outputs,
)
from pipelex.cli.dev_cli.commands.error_registry.type_redirects import write_type_redirects
from pipelex.runtime_hub import get_console

if TYPE_CHECKING:
    from pathlib import Path


def _print_faults(*, heading: str, errors: list[str]) -> None:
    console = get_console()
    console.print(f"[bold red]{heading}[/bold red]")
    for error in errors:
        console.print(f"  - {error}", markup=False, highlight=False)


def generate_error_registry_cmd(*, quiet: bool = False) -> None:
    """Write the registry's snapshot, its typed Python and its documentation pages, from its source and Pipelex's version.

    Nothing is written when the source has a fault: the faults are printed, and the command exits with 1.
    """
    console = get_console()
    checked, errors = source_errors()
    if checked is None:
        _print_faults(heading="The error registry is invalid, so nothing was written:", errors=errors)
        raise typer.Exit(1)
    report = write_outputs(outputs=render_outputs(checked=checked))
    if quiet:
        console.print(
            f"Error registry: {len(report.written)} written, {len(report.unchanged)} unchanged, {len(report.removed)} removed",
            markup=False,
            highlight=False,
        )
        return
    console.print(summary_line(checked=checked), markup=False, highlight=False)
    for path in report.written:
        console.print(f"  wrote {path}", markup=False, highlight=False)
    for path in report.removed:
        console.print(f"  removed {path}", markup=False, highlight=False)
    console.print(f"  {len(report.unchanged)} files unchanged", markup=False, highlight=False)


def check_error_registry_cmd(*, quiet: bool = False) -> None:
    """Check the registry, the standard's vendored files and every derived file, and exit with 1 on any fault."""
    console = get_console()
    checked, errors = check_error_registry()
    if errors or checked is None:
        _print_faults(heading="Error registry check FAILED:", errors=errors)
        console.print("Run `make generate-error-registry` to rewrite the derived files, after fixing the source.", markup=False, highlight=False)
        raise typer.Exit(1)
    line = summary_line(checked=checked)
    console.print(f"{line}: consistent" if not quiet else f"Error registry {checked.registry.version}: consistent", markup=False, highlight=False)


def write_error_type_redirects_cmd(*, site_root: Path, quiet: bool = False) -> None:
    """Write, at the root of the published documentation, the stub that makes each code's type URI reach its page."""
    console = get_console()
    checked, errors = source_errors()
    if checked is None:
        _print_faults(heading="The error registry is invalid, so no redirect was written:", errors=errors)
        raise typer.Exit(1)
    report = write_type_redirects(site_root=site_root, base_url=checked.registry.base_url)
    console.print(
        f"Error type redirects: {len(report.written)} written, {len(report.unchanged)} unchanged, {len(report.removed)} removed",
        markup=False,
        highlight=False,
    )
    if not quiet:
        for code in report.written:
            console.print(f"  wrote {code}", markup=False, highlight=False)
        for code in report.removed:
            console.print(f"  removed {code}", markup=False, highlight=False)
