import subprocess  # noqa: S404
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from pipelex.core.packages.exceptions import PublishValidationError
from pipelex.core.packages.publish_validation import PublishValidationResult, validate_for_publish
from pipelex.hub import get_console


def do_pkg_publish(tag: bool = False) -> None:
    """Validate package readiness for distribution.

    Args:
        tag: If True and validation passes, create a local git tag v{version}.
    """
    console = get_console()
    package_root = Path.cwd()

    try:
        result = validate_for_publish(package_root)
    except PublishValidationError as exc:
        console.print(f"[red]Error: {escape(exc.message)}[/red]")
        raise typer.Exit(code=1) from exc

    _display_results(console, result)

    errors = [issue for issue in result.issues if issue.level.is_error]
    warnings = [issue for issue in result.issues if issue.level.is_warning]

    console.print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")

    if errors:
        console.print("[red]Package is NOT ready for distribution.[/red]")
        raise typer.Exit(code=1)

    if tag and result.package_version:
        _create_git_tag(console, package_root, result.package_version)

    console.print("[green]Package is ready for distribution.[/green]")


def _display_results(console: Console, result: PublishValidationResult) -> None:
    """Display validation issues as Rich tables."""
    errors = [issue for issue in result.issues if issue.level.is_error]
    warnings = [issue for issue in result.issues if issue.level.is_warning]

    if errors:
        error_table = Table(title="Errors", box=box.ROUNDED, show_header=True)
        error_table.add_column("Category", style="red")
        error_table.add_column("Message", style="red")
        error_table.add_column("Suggestion", style="dim")

        for issue in errors:
            error_table.add_row(
                issue.category,
                issue.message,
                issue.suggestion or "",
            )

        console.print(error_table)

    if warnings:
        warning_table = Table(title="Warnings", box=box.ROUNDED, show_header=True)
        warning_table.add_column("Category", style="yellow")
        warning_table.add_column("Message", style="yellow")
        warning_table.add_column("Suggestion", style="dim")

        for issue in warnings:
            warning_table.add_row(
                issue.category,
                issue.message,
                issue.suggestion or "",
            )

        console.print(warning_table)


def _create_git_tag(console: Console, package_root: Path, version: str) -> None:
    """Create a local git tag from the already-validated package version."""
    version_tag = f"v{version}"

    try:
        subprocess.run(  # noqa: S603
            ["git", "tag", version_tag],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
            cwd=package_root,
        )
        console.print(f"[green]Created git tag '{escape(version_tag)}'[/green]")
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Failed to create git tag: {escape(exc.stderr.strip())}[/red]")
        raise typer.Exit(code=1) from exc
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        console.print("[red]Failed to create git tag: git not available[/red]")
        raise typer.Exit(code=1) from exc
