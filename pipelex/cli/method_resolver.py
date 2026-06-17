from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

import typer
from mthds.package.exceptions import VCSFetchError
from mthds.package.vcs_resolver import clone_default_branch

from pipelex.cli.installed_methods import (
    DuplicateMethodNameError,
    InstalledMethod,
    MethodNotFoundError,
    discover_installed_methods,
    discover_method_at,
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


def is_github_url(target: str) -> bool:
    """Return True if *target* looks like a GitHub URL."""
    return target.startswith(("https://github.com/", "http://github.com/"))


def parse_github_url(url: str) -> tuple[str, str | None]:
    """Extract an HTTPS clone URL and optional sub-path from a GitHub URL.

    Handles plain repo URLs (``https://github.com/org/repo``), repo URLs
    with a trailing ``.git``, and subdirectory URLs such as
    ``https://github.com/org/repo/tree/branch/path/to/dir`` or the shorthand
    ``https://github.com/org/repo/path/to/dir`` that GitHub auto-resolves.

    Args:
        url: A GitHub URL pointing to a repository or a subdirectory within it.

    Returns:
        A tuple of (clone_url, sub_path).  *sub_path* is ``None`` when the URL
        points to the repository root.
    """
    clean = url.rstrip("/")

    # Strip .git suffix before parsing
    if clean.endswith(".git"):
        return (clean, None)

    # Split off the scheme + github.com prefix
    # URL looks like https://github.com/owner/repo[/rest...]
    for prefix in ("https://github.com/", "http://github.com/"):
        if clean.startswith(prefix):
            remainder = clean[len(prefix) :]
            break
    else:
        # Should not happen since callers check is_github_url first
        clone_url = f"{clean}.git"
        return (clone_url, None)

    parts = remainder.split("/")
    if len(parts) < 2:
        clone_url = f"{clean}.git"
        return (clone_url, None)

    owner = parts[0]
    repo = parts[1]
    scheme = "https" if clean.startswith("https") else "http"
    clone_url = f"{scheme}://github.com/{owner}/{repo}.git"

    # No extra path segments → repo root
    if len(parts) <= 2:
        return (clone_url, None)

    # Handle /tree/<branch>/path/... or /blob/<branch>/path/...
    rest = parts[2:]
    if rest[0] in {"tree", "blob"} and len(rest) >= 2:
        # Skip the segment type and branch name
        sub_parts = rest[2:]
        sub_path = "/".join(sub_parts) if sub_parts else None
    else:
        # Shorthand: https://github.com/owner/repo/path/to/dir
        sub_path = "/".join(rest)

    return (clone_url, sub_path or None)


def is_local_path(target: str) -> bool:
    """Return True if *target* looks like a filesystem path (absolute or relative with separators)."""
    if target.startswith(("https://", "http://")):
        return False
    return "/" in target or "\\" in target


def resolve_method_from_path(method_path: str) -> InstalledMethod:
    """Discover a method package from a local filesystem path.

    Args:
        method_path: A filesystem path to a directory containing a method package.

    Returns:
        The discovered ``InstalledMethod``.

    Raises:
        typer.Exit: If the path doesn't exist or contains no method package.
    """
    method_dir = Path(method_path)
    if not method_dir.is_dir():
        typer.secho(
            f"Directory '{method_path}' does not exist.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    seen_dirs: set[Path] = set()
    method = discover_method_at(method_dir, seen_dirs=seen_dirs)
    if method is None:
        typer.secho(
            f"No method package (METHODS.toml) found at '{method_path}'.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    return method


def resolve_method_from_url(url: str) -> InstalledMethod:
    """Clone a remote repository and discover the method package inside it.

    Supports both repo-root URLs (``https://github.com/org/repo``) and
    subdirectory URLs (``https://github.com/org/repo/tree/main/path/to/method``
    or the shorthand ``https://github.com/org/repo/path/to/method``).

    Uses a temporary directory that persists for the duration of the CLI
    process, so the cloned files remain available for subsequent steps.

    Args:
        url: A GitHub URL pointing to a repository or subdirectory
            containing a method package.

    Returns:
        The discovered ``InstalledMethod``.

    Raises:
        typer.Exit: On clone failure or if no method package is found.
    """
    clone_url, sub_path = parse_github_url(url)
    dest = Path(tempfile.mkdtemp(prefix="mthds_remote_"))
    atexit.register(shutil.rmtree, dest, True)

    try:
        clone_default_branch(clone_url, dest)
    except VCSFetchError as exc:
        typer.secho(
            f"Failed to clone repository from '{url}': {exc.message}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1) from exc

    # Determine the method directory (repo root or a sub-path within it)
    method_dir = dest / sub_path if sub_path else dest

    if not method_dir.is_dir():
        typer.secho(
            f"Path '{sub_path}' not found in the cloned repository from '{url}'.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    # Discover the method package
    seen_dirs: set[Path] = set()
    method = discover_method_at(method_dir, seen_dirs=seen_dirs)
    if method is None:
        typer.secho(
            f"No method package (METHODS.toml) found at '{url}'.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    return method


def resolve_method_target(
    method_name: str,
    *,
    pipe_override: str | None = None,
    library_dirs: list[str] | None = None,
) -> tuple[str, list[str], InstalledMethod]:
    """Resolve a method name or GitHub URL to (pipe_code, library_dirs, method).

    Finds the installed method by name (or clones from a GitHub URL),
    determines the pipe to run (using pipe_override or main_pipe), and
    returns the library directories needed to load the method's bundles
    along with the method itself.

    Args:
        method_name: The installed method name or GitHub URL to resolve.
        pipe_override: Optional pipe code override (takes precedence over main_pipe).
        library_dirs: Additional directories to search for methods.

    Returns:
        A tuple of (pipe_code, library_dirs, installed_method) for execution.

    Raises:
        typer.Exit: On resolution errors with user-friendly messages.
    """
    method: InstalledMethod
    if is_github_url(method_name):
        method = resolve_method_from_url(method_name)
    elif is_local_path(method_name):
        method = resolve_method_from_path(method_name)
    else:
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
