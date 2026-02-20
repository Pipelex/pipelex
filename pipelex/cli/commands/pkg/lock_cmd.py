from pathlib import Path

import typer
from rich.markup import escape

from pipelex.core.packages.dependency_resolver import resolve_all_dependencies
from pipelex.core.packages.discovery import MANIFEST_FILENAME
from pipelex.core.packages.exceptions import DependencyResolveError, ManifestError, TransitiveDependencyError
from pipelex.core.packages.lock_file import LOCK_FILENAME, LockFileError, generate_lock_file, serialize_lock_file
from pipelex.core.packages.manifest_parser import parse_methods_toml
from pipelex.hub import get_console


def do_pkg_lock() -> None:
    """Resolve dependencies and generate methods.lock."""
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
        console.print(f"[red]Could not parse {MANIFEST_FILENAME}: {escape(exc.message)}[/red]")
        raise typer.Exit(code=1) from exc

    try:
        resolved = resolve_all_dependencies(manifest, cwd)
    except (DependencyResolveError, TransitiveDependencyError) as exc:
        console.print(f"[red]Dependency resolution failed: {escape(exc.message)}[/red]")
        raise typer.Exit(code=1) from exc

    try:
        lock = generate_lock_file(manifest, resolved)
    except LockFileError as exc:
        console.print(f"[red]Lock file generation failed: {escape(exc.message)}[/red]")
        raise typer.Exit(code=1) from exc

    lock_content = serialize_lock_file(lock)
    lock_path = cwd / LOCK_FILENAME
    lock_path.write_text(lock_content, encoding="utf-8")

    pkg_count = len(lock.packages)
    console.print(f"[green]Wrote {LOCK_FILENAME} with {pkg_count} package(s).[/green]")
