from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

import typer

from pipelex.cli.installed_methods import (
    DuplicateMethodNameError,
    InstalledMethod,
    MethodNotFoundError,
    discover_installed_methods,
    discover_method_at,
    find_method_by_name,
)
from pipelex.methods.exceptions import MethodRefError
from pipelex.methods.fetching import fetch_method_package
from pipelex.methods.method_ref import looks_like_method_ref, parse_method_ref
from pipelex.methods.structures_check import (
    STRUCTURES_REFUSAL_RULE,
    describe_structured_content_violations,
    scan_structured_content_classes,
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


def resolve_method_from_ref(ref_str: str) -> InstalledMethod:
    """Fetch a method by reference (`<address>[@<tag>]` or a GitHub URL) and discover it.

    Clones the repository (at the tag when one is named), locates the package inside the
    clone by manifest identity, prints the fetch provenance (address, tag, commit SHA),
    and warns — hosted parity — when the package declares in-process Python structure
    classes that hosted execution would refuse.

    Uses a temporary directory that persists for the duration of the CLI process, so the
    fetched files remain available for subsequent steps. Failures raise the typed
    ``MethodRefError`` family — presentation is the caller's concern: the human CLI
    renders them through ``resolve_method_target``, the agent CLI shapes them into its
    structured error envelope.

    Args:
        ref_str: The method reference string.

    Returns:
        The discovered ``InstalledMethod``, carrying the fetch provenance.

    Raises:
        MethodRefError: On a parse, fetch, location, bounds, or refusal failure
            (the concrete subclass names which).
    """
    method_ref = parse_method_ref(ref_str)

    dest = Path(tempfile.mkdtemp(prefix="mthds_remote_"))
    atexit.register(shutil.rmtree, dest, True)

    fetched = fetch_method_package(ref=method_ref, dest_dir=dest)

    typer.secho(
        f"Fetched {fetched.full_address}{f'@{method_ref.tag}' if method_ref.tag else ''} at commit {fetched.commit_sha}",
        fg=typer.colors.GREEN,
        err=True,
    )

    violations = scan_structured_content_classes(package_dir=fetched.package_dir)
    if violations:
        details = describe_structured_content_violations(violations=violations)
        typer.secho(
            f"Warning: this method declares Python structure classes ({details}). It runs locally, but {STRUCTURES_REFUSAL_RULE} — "
            f"hosted execution would refuse it. Express the types as MTHDS concepts to keep the method hosted-runnable.",
            fg=typer.colors.YELLOW,
            err=True,
        )

    name = fetched.manifest.name or fetched.package_dir.name
    return InstalledMethod(
        name=name,
        path=fetched.package_dir,
        manifest=fetched.manifest,
        mthds_files=sorted(fetched.package_dir.rglob("*.mthds")),
        provenance=fetched.provenance,
    )


def resolve_method_target(
    method_name: str,
    *,
    pipe_override: str | None = None,
    library_dirs: list[str] | None = None,
    raise_ref_errors: bool = False,
) -> tuple[str, list[str], InstalledMethod]:
    """Resolve a method name, address, URL, or local path to (pipe_code, library_dirs, method).

    Finds the installed method by name (or fetches it by method reference — a bare
    `github.com/...` address, optionally `@<tag>`-pinned, or a full GitHub URL — or
    discovers it at a local path), determines the pipe to run (using pipe_override or
    main_pipe), and returns the library directories needed to load the method's bundles
    along with the method itself.

    Args:
        method_name: The installed method name, method reference, or local path to resolve.
        pipe_override: Optional pipe code override (takes precedence over main_pipe).
        library_dirs: Additional directories to search for methods.
        raise_ref_errors: When True, a method-reference failure propagates as its typed
            ``MethodRefError`` instead of being rendered and turned into ``typer.Exit`` —
            the agent CLI commands pass True so their structured error envelope (not
            plain red text) reports the failure.

    Returns:
        A tuple of (pipe_code, library_dirs, installed_method) for execution.

    Raises:
        typer.Exit: On resolution errors with user-friendly messages.
        MethodRefError: On a method-reference failure, when ``raise_ref_errors`` is True.
    """
    method: InstalledMethod
    if looks_like_method_ref(method_name):
        if raise_ref_errors:
            method = resolve_method_from_ref(method_name)
        else:
            try:
                method = resolve_method_from_ref(method_name)
            except MethodRefError as exc:
                typer.secho(str(exc), fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
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


def method_output_base_dir(*, method: InstalledMethod) -> Path:
    """Base directory anchoring a method target's default output paths.

    An installed or local-path method anchors its outputs in its own directory. A fetched
    method's directory is an ephemeral clone deleted at process exit, so anchoring outputs
    there would silently lose them — a fetched method anchors in the caller's current
    working directory instead, where a run's results survive the process.

    Args:
        method: The resolved method target.

    Returns:
        The directory default output paths should be built under.
    """
    if method.provenance is None:
        return method.path
    return Path.cwd()


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
