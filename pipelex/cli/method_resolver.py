from __future__ import annotations

import typer

from pipelex.cli.installed_methods import (
    DuplicateMethodNameError,
    InstalledMethod,
    MethodNotFoundError,
    discover_installed_methods,
    find_method_by_name,
)


def _get_all_exported_pipes(method: InstalledMethod) -> set[str]:
    """Collect all pipe codes from a method's exports (all domains)."""
    pipe_codes: set[str] = set()
    for domain_exports in method.manifest.exports.values():
        pipe_codes.update(domain_exports.pipes)
    return pipe_codes


def _find_method_by_exported_pipe(pipe_code: str) -> InstalledMethod:
    """Find which installed method exports a given pipe code.

    Scans all methods' exports sections for matching pipe codes.

    Args:
        pipe_code: The pipe code to search for

    Returns:
        The installed method that exports the given pipe code

    Raises:
        LookupError: If the pipe code is not found in any method's exports
        ValueError: If the pipe code is found in multiple methods
    """
    methods = discover_installed_methods()

    matches: list[InstalledMethod] = []
    for method in methods:
        if pipe_code in _get_all_exported_pipes(method):
            matches.append(method)

    if len(matches) == 0:
        msg = f"Pipe code '{pipe_code}' not found in any installed method's exports."
        raise LookupError(msg)
    if len(matches) > 1:
        method_names = ", ".join(method.name for method in matches)
        msg = f"Pipe code '{pipe_code}' is exported by multiple methods: {method_names}"
        raise ValueError(msg)

    return matches[0]


def resolve_method_target(
    method_name: str,
    pipe_override: str | None = None,
    library_dirs: list[str] | None = None,
) -> tuple[str, list[str], InstalledMethod]:
    """Resolve a method name to (pipe_code, library_dirs, method).

    Finds the installed method by name, determines the pipe to run
    (using pipe_override or main_pipe), and returns the library directories
    needed to load the method's bundles along with the method itself.

    Args:
        method_name: The installed method name to resolve.
        pipe_override: Optional pipe code override (takes precedence over main_pipe).
        library_dirs: Additional directories to search for methods.

    Returns:
        A tuple of (pipe_code, library_dirs, installed_method) for execution.

    Raises:
        typer.Exit: On resolution errors with user-friendly messages.
    """
    try:
        method = find_method_by_name(method_name, library_dirs=library_dirs)
    except MethodNotFoundError as exc:
        typer.secho(
            f"Method '{method_name}' is not installed. Check installed methods with: ls ~/.mthds/methods/ or ls .mthds/methods/",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1) from exc
    except DuplicateMethodNameError as exc:
        typer.secho(
            f"Ambiguous method name '{method_name}': {exc.message}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1) from exc

    # Determine pipe code
    pipe_code: str
    if pipe_override:
        pipe_code = pipe_override
    elif method.manifest.main_pipe:
        pipe_code = method.manifest.main_pipe
    else:
        typer.secho(
            f"Method '{method_name}' does not declare a main_pipe. Specify a pipe code with --pipe.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    # The method directory is a library directory
    library_dirs = [str(method.path)]

    return pipe_code, library_dirs, method


def resolve_pipe_from_exports(
    pipe_code: str,
) -> list[str] | None:
    """Check installed methods' exports for a pipe code.

    If found in exactly one method, returns the library dirs for that method.
    If not found, returns None (caller should proceed without extra dirs).

    Args:
        pipe_code: The pipe code to look up in installed methods' exports.

    Returns:
        Library dirs if the pipe code was found in an installed method, None otherwise.

    Raises:
        ValueError: If the pipe code is found in multiple methods (ambiguous).
    """
    try:
        method = _find_method_by_exported_pipe(pipe_code)
        return [str(method.path)]
    except LookupError:
        return None
