from pathlib import Path

import typer

from pipelex.core.packages.dependency_resolver import resolve_remote_dependency
from pipelex.core.packages.exceptions import DependencyResolveError, IntegrityError
from pipelex.core.packages.lock_file import LOCK_FILENAME, LockFileError, parse_lock_file, verify_lock_file
from pipelex.core.packages.manifest import PackageDependency
from pipelex.core.packages.package_cache import is_cached
from pipelex.hub import get_console


def do_pkg_install() -> None:
    """Install dependencies from methods.lock."""
    console = get_console()
    cwd = Path.cwd()
    lock_path = cwd / LOCK_FILENAME

    if not lock_path.exists():
        console.print(f"[red]{LOCK_FILENAME} not found in current directory.[/red]")
        console.print("Run [bold]pipelex pkg lock[/bold] first to generate a lock file.")
        raise typer.Exit(code=1)

    lock_content = lock_path.read_text(encoding="utf-8")
    try:
        lock_file = parse_lock_file(lock_content)
    except LockFileError as exc:
        console.print(f"[red]Could not parse {LOCK_FILENAME}: {exc.message}[/red]")
        raise typer.Exit(code=1) from exc

    if not lock_file.packages:
        console.print("[dim]Nothing to install — lock file is empty.[/dim]")
        return

    fetched_count = 0
    cached_count = 0

    for address, locked in lock_file.packages.items():
        if is_cached(address, locked.version):
            cached_count += 1
            continue

        # Fetch missing package by resolving with exact version constraint
        dep = PackageDependency(
            address=address,
            version=locked.version,
            alias=address.rsplit("/", maxsplit=1)[-1].replace("-", "_").replace(".", "_"),
        )
        try:
            resolve_remote_dependency(dep)
        except DependencyResolveError as exc:
            console.print(f"[red]Failed to fetch '{address}@{locked.version}': {exc.message}[/red]")
            raise typer.Exit(code=1) from exc

        fetched_count += 1

    # Verify integrity
    try:
        verify_lock_file(lock_file)
    except IntegrityError as exc:
        console.print(f"[red]Integrity verification failed: {exc.message}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Installed {fetched_count} package(s), {cached_count} already cached.[/green]")
