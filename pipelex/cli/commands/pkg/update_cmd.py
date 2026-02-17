from pathlib import Path

import typer
from rich.console import Console

from pipelex.core.packages.dependency_resolver import resolve_all_dependencies
from pipelex.core.packages.discovery import MANIFEST_FILENAME
from pipelex.core.packages.exceptions import DependencyResolveError, ManifestError, TransitiveDependencyError
from pipelex.core.packages.lock_file import (
    LOCK_FILENAME,
    LockFile,
    LockFileError,
    generate_lock_file,
    parse_lock_file,
    serialize_lock_file,
)
from pipelex.core.packages.manifest_parser import parse_methods_toml
from pipelex.hub import get_console


def _display_lock_diff(console: Console, old_lock: LockFile, new_lock: LockFile) -> None:
    """Display differences between an old and new lock file.

    Args:
        console: Rich console for output.
        old_lock: The previous lock file.
        new_lock: The freshly generated lock file.
    """
    old_addresses = set(old_lock.packages)
    new_addresses = set(new_lock.packages)

    added = new_addresses - old_addresses
    removed = old_addresses - new_addresses
    common = old_addresses & new_addresses

    updated: list[str] = []
    for address in sorted(common):
        old_ver = old_lock.packages[address].version
        new_ver = new_lock.packages[address].version
        if old_ver != new_ver:
            updated.append(f"{address}: {old_ver} -> {new_ver}")

    if not added and not removed and not updated:
        console.print("[dim]No changes — lock file is up to date.[/dim]")
        return

    for address in sorted(added):
        version = new_lock.packages[address].version
        console.print(f"  [green]+ {address}@{version}[/green]")

    for address in sorted(removed):
        version = old_lock.packages[address].version
        console.print(f"  [red]- {address}@{version}[/red]")

    for line in updated:
        console.print(f"  [yellow]{line}[/yellow]")


def do_pkg_update() -> None:
    """Re-resolve dependencies and update methods.lock."""
    console = get_console()
    cwd = Path.cwd()
    manifest_path = cwd / MANIFEST_FILENAME

    if not manifest_path.exists():
        console.print(f"[red]{MANIFEST_FILENAME} not found in current directory.[/red]")
        console.print("Run [bold]pipelex pkg init[/bold] first to create a manifest.")
        raise typer.Exit(code=1)

    content = manifest_path.read_text(encoding="utf-8")
    try:
        manifest = parse_methods_toml(content)
    except ManifestError as exc:
        console.print(f"[red]Could not parse {MANIFEST_FILENAME}: {exc.message}[/red]")
        raise typer.Exit(code=1) from exc

    # Read existing lock for diff comparison
    lock_path = cwd / LOCK_FILENAME
    old_lock: LockFile | None = None
    if lock_path.exists():
        try:
            old_lock = parse_lock_file(lock_path.read_text(encoding="utf-8"))
        except LockFileError:
            pass  # Ignore unparseable old lock

    # Fresh resolve (ignoring existing lock)
    try:
        resolved = resolve_all_dependencies(manifest, cwd)
    except (DependencyResolveError, TransitiveDependencyError) as exc:
        console.print(f"[red]Dependency resolution failed: {exc.message}[/red]")
        raise typer.Exit(code=1) from exc

    try:
        new_lock = generate_lock_file(manifest, resolved)
    except LockFileError as exc:
        console.print(f"[red]Lock file generation failed: {exc.message}[/red]")
        raise typer.Exit(code=1) from exc

    # Write lock file
    lock_content = serialize_lock_file(new_lock)
    lock_path.write_text(lock_content, encoding="utf-8")

    pkg_count = len(new_lock.packages)
    console.print(f"[green]Wrote {LOCK_FILENAME} with {pkg_count} package(s).[/green]")

    # Display diff
    if old_lock is not None:
        _display_lock_diff(console, old_lock, new_lock)
    else:
        console.print("[dim]No previous lock file — created fresh.[/dim]")
