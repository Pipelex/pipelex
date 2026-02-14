# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from pipelex import log
from pipelex.core.packages.discovery import MANIFEST_FILENAME, find_package_manifest
from pipelex.core.packages.exceptions import (
    DependencyResolveError,
    ManifestError,
    PackageCacheError,
    TransitiveDependencyError,
    VCSFetchError,
    VersionResolutionError,
)
from pipelex.core.packages.manifest import MthdsPackageManifest, PackageDependency
from pipelex.core.packages.package_cache import get_cached_package_path, is_cached, store_in_cache
from pipelex.core.packages.vcs_resolver import address_to_clone_url, clone_at_version, list_remote_version_tags, resolve_version_from_tags
from pipelex.tools.misc.semver import parse_constraint, parse_version, select_minimum_version_for_multiple_constraints, version_satisfies


class ResolvedDependency(BaseModel):
    """A resolved local dependency with its manifest and file paths."""

    model_config = ConfigDict(frozen=True)

    alias: str
    address: str
    manifest: MthdsPackageManifest | None
    package_root: Path
    mthds_files: list[Path]
    exported_pipe_codes: set[str] | None


def collect_mthds_files(directory: Path) -> list[Path]:
    """Collect all .mthds files under a directory recursively.

    Args:
        directory: The directory to scan

    Returns:
        List of .mthds file paths found
    """
    return sorted(directory.rglob("*.mthds"))


def determine_exported_pipes(manifest: MthdsPackageManifest | None) -> set[str] | None:
    """Determine which pipes are exported by a dependency.

    Returns None when all pipes should be public (no manifest, or manifest
    without an ``[[exports]]`` section). Returns a set of pipe codes when
    the manifest explicitly declares exports (the set may be empty if
    export entries list no pipes, meaning only ``main_pipe`` is public).

    Args:
        manifest: The dependency's manifest (if any)

    Returns:
        None if all pipes are public, or the set of explicitly exported pipe codes.
    """
    if manifest is None:
        return None

    # No exports section in manifest -> all pipes are public
    if not manifest.exports:
        return None

    exported: set[str] = set()
    for domain_export in manifest.exports:
        exported.update(domain_export.pipes)

    # Auto-export main_pipe from bundles (scan for main_pipe in bundle headers)
    # This is done at loading time by LibraryManager, not here
    return exported


def resolve_local_dependencies(
    manifest: MthdsPackageManifest,
    package_root: Path,
) -> list[ResolvedDependency]:
    """Resolve dependencies that have a local `path` field.

    For each dependency with a `path`, resolves the directory, finds the manifest
    and .mthds files, and determines exported pipes.

    Args:
        manifest: The consuming package's manifest
        package_root: The root directory of the consuming package

    Returns:
        List of resolved dependencies (only those with a `path` field)

    Raises:
        DependencyResolveError: If a path does not exist or is not a directory
    """
    resolved: list[ResolvedDependency] = []

    for dep in manifest.dependencies:
        if dep.path is None:
            log.verbose(f"Dependency '{dep.alias}' has no local path, skipping local resolution")
            continue

        dep_dir = (package_root / dep.path).resolve()
        if not dep_dir.exists():
            msg = f"Dependency '{dep.alias}' local path '{dep.path}' resolves to '{dep_dir}' which does not exist"
            raise DependencyResolveError(msg)
        if not dep_dir.is_dir():
            msg = f"Dependency '{dep.alias}' local path '{dep.path}' resolves to '{dep_dir}' which is not a directory"
            raise DependencyResolveError(msg)

        # Find the dependency's manifest
        dep_manifest: MthdsPackageManifest | None = None
        dep_manifest_path = dep_dir / MANIFEST_FILENAME
        if dep_manifest_path.is_file():
            try:
                dep_manifest = find_package_manifest(dep_manifest_path)
            except ManifestError as exc:
                log.warning(f"Could not parse METHODS.toml for dependency '{dep.alias}': {exc.message}")

        # Collect .mthds files
        mthds_files = collect_mthds_files(dep_dir)

        # Determine exported pipes
        exported_pipe_codes = determine_exported_pipes(dep_manifest)

        resolved.append(
            ResolvedDependency(
                alias=dep.alias,
                address=dep.address,
                manifest=dep_manifest,
                package_root=dep_dir,
                mthds_files=mthds_files,
                exported_pipe_codes=exported_pipe_codes,
            )
        )
        export_count = len(exported_pipe_codes) if exported_pipe_codes is not None else "all"
        log.verbose(f"Resolved dependency '{dep.alias}': {len(mthds_files)} .mthds files, {export_count} exported pipes")

    return resolved


def _find_manifest_in_dir(directory: Path) -> MthdsPackageManifest | None:
    """Read and parse a METHODS.toml from a directory root.

    Args:
        directory: The directory to look for METHODS.toml in.

    Returns:
        The parsed manifest, or None if absent or unparseable.
    """
    manifest_path = directory / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None
    try:
        return find_package_manifest(manifest_path)
    except ManifestError as exc:
        log.warning(f"Could not parse METHODS.toml in '{directory}': {exc.message}")
        return None


def _resolve_local_dependency(
    dep: PackageDependency,
    package_root: Path,
) -> ResolvedDependency:
    """Resolve a single dependency that has a local path.

    Args:
        dep: The dependency with a non-None ``path`` field.
        package_root: The consuming package root.

    Returns:
        The resolved dependency.

    Raises:
        DependencyResolveError: If the path does not exist or is not a directory.
    """
    local_path: str = dep.path  # type: ignore[assignment]
    dep_dir = (package_root / local_path).resolve()
    if not dep_dir.exists():
        msg = f"Dependency '{dep.alias}' local path '{local_path}' resolves to '{dep_dir}' which does not exist"
        raise DependencyResolveError(msg)
    if not dep_dir.is_dir():
        msg = f"Dependency '{dep.alias}' local path '{local_path}' resolves to '{dep_dir}' which is not a directory"
        raise DependencyResolveError(msg)

    dep_manifest = _find_manifest_in_dir(dep_dir)
    mthds_files = collect_mthds_files(dep_dir)
    exported_pipe_codes = determine_exported_pipes(dep_manifest)

    return ResolvedDependency(
        alias=dep.alias,
        address=dep.address,
        manifest=dep_manifest,
        package_root=dep_dir,
        mthds_files=mthds_files,
        exported_pipe_codes=exported_pipe_codes,
    )


def resolve_remote_dependency(
    dep: PackageDependency,
    cache_root: Path | None = None,
    fetch_url_override: str | None = None,
) -> ResolvedDependency:
    """Resolve a single dependency via VCS fetch (with cache).

    Orchestrates: get clone URL -> list remote tags -> MVS version selection ->
    check cache -> clone if miss -> build ResolvedDependency.

    Args:
        dep: The dependency to resolve (no ``path`` field).
        cache_root: Override for the package cache root directory.
        fetch_url_override: Override clone URL (e.g. ``file://`` for tests).

    Returns:
        The resolved dependency.

    Raises:
        DependencyResolveError: If fetching or version resolution fails.
    """
    clone_url = fetch_url_override or address_to_clone_url(dep.address)

    # List remote tags and select version
    try:
        version_tags = list_remote_version_tags(clone_url)
        selected_version, selected_tag = resolve_version_from_tags(version_tags, dep.version)
    except (VCSFetchError, VersionResolutionError) as exc:
        msg = f"Failed to resolve remote dependency '{dep.alias}' ({dep.address}): {exc}"
        raise DependencyResolveError(msg) from exc

    version_str = str(selected_version)

    # Check cache
    if is_cached(dep.address, version_str, cache_root):
        cached_path = get_cached_package_path(dep.address, version_str, cache_root)
        log.verbose(f"Dependency '{dep.alias}' ({dep.address}@{version_str}) found in cache")
        return _build_resolved_from_dir(dep.alias, dep.address, cached_path)

    # Clone and cache
    try:
        with tempfile.TemporaryDirectory(prefix="mthds_clone_") as tmp_dir:
            clone_dest = Path(tmp_dir) / "pkg"
            clone_at_version(clone_url, selected_tag, clone_dest)
            cached_path = store_in_cache(clone_dest, dep.address, version_str, cache_root)
    except (VCSFetchError, PackageCacheError) as exc:
        msg = f"Failed to fetch/cache dependency '{dep.alias}' ({dep.address}@{version_str}): {exc}"
        raise DependencyResolveError(msg) from exc

    log.verbose(f"Dependency '{dep.alias}' ({dep.address}@{version_str}) fetched and cached")
    return _build_resolved_from_dir(dep.alias, dep.address, cached_path)


def _build_resolved_from_dir(alias: str, address: str, directory: Path) -> ResolvedDependency:
    """Build a ResolvedDependency from a package directory.

    Args:
        alias: The dependency alias.
        address: The package address.
        directory: The package directory (local or cached).

    Returns:
        The resolved dependency.
    """
    dep_manifest = _find_manifest_in_dir(directory)
    mthds_files = collect_mthds_files(directory)
    exported_pipe_codes = determine_exported_pipes(dep_manifest)

    return ResolvedDependency(
        alias=alias,
        address=address,
        manifest=dep_manifest,
        package_root=directory,
        mthds_files=mthds_files,
        exported_pipe_codes=exported_pipe_codes,
    )


def _resolve_with_multiple_constraints(
    address: str,
    alias: str,
    constraints: list[str],
    tags_cache: dict[str, list[tuple[Any, str]]],
    cache_root: Path | None,
    fetch_url_override: str | None,
) -> ResolvedDependency:
    """Resolve a dependency that has multiple version constraints (diamond).

    Gets/caches the remote tag list, parses all constraints, and selects the
    minimum version satisfying all of them simultaneously.

    Args:
        address: The package address.
        alias: The dependency alias.
        constraints: All version constraint strings from different dependents.
        tags_cache: Shared cache of address -> tag list.
        cache_root: Override for the package cache root.
        fetch_url_override: Override clone URL (for tests).

    Returns:
        The resolved dependency.

    Raises:
        TransitiveDependencyError: If no version satisfies all constraints.
        DependencyResolveError: If VCS operations fail.
    """
    clone_url = fetch_url_override or address_to_clone_url(address)

    # Get or cache tag list
    if address not in tags_cache:
        try:
            tags_cache[address] = list_remote_version_tags(clone_url)
        except VCSFetchError as exc:
            msg = f"Failed to list tags for '{address}': {exc}"
            raise DependencyResolveError(msg) from exc

    version_tags = tags_cache[address]
    versions = [entry[0] for entry in version_tags]

    # Parse all constraints and find a version satisfying all
    parsed_constraints = [parse_constraint(constraint) for constraint in constraints]
    selected = select_minimum_version_for_multiple_constraints(versions, parsed_constraints)

    if selected is None:
        constraints_str = ", ".join(constraints)
        msg = f"No version of '{address}' satisfies all constraints: {constraints_str}"
        raise TransitiveDependencyError(msg)

    version_str = str(selected)

    # Check cache
    if is_cached(address, version_str, cache_root):
        cached_path = get_cached_package_path(address, version_str, cache_root)
        log.verbose(f"Diamond dep '{alias}' ({address}@{version_str}) found in cache")
        return _build_resolved_from_dir(alias, address, cached_path)

    # Find the corresponding tag name
    selected_tag: str | None = None
    for ver, tag_name in version_tags:
        if ver == selected:
            selected_tag = tag_name
            break

    if selected_tag is None:
        msg = f"Internal error: selected version {selected} not found in tag list for '{address}'"
        raise DependencyResolveError(msg)

    # Clone and cache
    try:
        with tempfile.TemporaryDirectory(prefix="mthds_clone_") as tmp_dir:
            clone_dest = Path(tmp_dir) / "pkg"
            clone_at_version(clone_url, selected_tag, clone_dest)
            cached_path = store_in_cache(clone_dest, address, version_str, cache_root)
    except (VCSFetchError, PackageCacheError) as exc:
        msg = f"Failed to fetch/cache '{address}@{version_str}': {exc}"
        raise DependencyResolveError(msg) from exc

    log.verbose(f"Diamond dep '{alias}' ({address}@{version_str}) fetched and cached")
    return _build_resolved_from_dir(alias, address, cached_path)


def _resolve_transitive_tree(
    deps: list[PackageDependency],
    resolution_stack: set[str],
    resolved_map: dict[str, ResolvedDependency],
    constraints_by_address: dict[str, list[str]],
    tags_cache: dict[str, list[tuple[Any, str]]],
    cache_root: Path | None,
    fetch_url_overrides: dict[str, str] | None,
) -> None:
    """Recursively resolve remote dependencies with cycle detection and diamond handling.

    Uses DFS with a stack set for cycle detection. Diamond dependencies (same address
    reached via multiple paths) are resolved by finding a version satisfying all constraints.

    Args:
        deps: Dependencies to resolve at this level.
        resolution_stack: Addresses currently on the DFS path (cycle detection).
        resolved_map: Address -> resolved dependency (deduplication).
        constraints_by_address: Address -> list of version constraints seen.
        tags_cache: Address -> cached tag list (avoid repeated git ls-remote).
        cache_root: Override for the package cache root.
        fetch_url_overrides: Map of address to override clone URL (for tests).

    Raises:
        TransitiveDependencyError: If a cycle is detected or diamond constraints are unsatisfiable.
        DependencyResolveError: If resolution fails.
    """
    for dep in deps:
        # Skip local path deps in transitive resolution
        if dep.path is not None:
            continue

        # Cycle detection
        if dep.address in resolution_stack:
            msg = f"Dependency cycle detected: '{dep.address}' is already on the resolution stack"
            raise TransitiveDependencyError(msg)

        # Track constraint
        if dep.address not in constraints_by_address:
            constraints_by_address[dep.address] = []
        constraints_by_address[dep.address].append(dep.version)

        # Already resolved — check if existing version satisfies new constraint
        if dep.address in resolved_map:
            existing = resolved_map[dep.address]
            if existing.manifest is not None:
                existing_constraint = parse_constraint(dep.version)
                existing_ver = parse_version(existing.manifest.version)
                if version_satisfies(existing_ver, existing_constraint):
                    log.verbose(f"Transitive dep '{dep.address}' already resolved at {existing.manifest.version}, satisfies '{dep.version}'")
                    continue

            # Diamond: re-resolve with all constraints
            override_url = (fetch_url_overrides or {}).get(dep.address)
            re_resolved = _resolve_with_multiple_constraints(
                address=dep.address,
                alias=dep.alias,
                constraints=constraints_by_address[dep.address],
                tags_cache=tags_cache,
                cache_root=cache_root,
                fetch_url_override=override_url,
            )
            resolved_map[dep.address] = re_resolved

            # Recurse into sub-dependencies of the re-resolved version,
            # which may differ from the previously resolved version
            if re_resolved.manifest is not None and re_resolved.manifest.dependencies:
                remote_sub_deps = [sub for sub in re_resolved.manifest.dependencies if sub.path is None]
                if remote_sub_deps:
                    resolution_stack.add(dep.address)
                    try:
                        _resolve_transitive_tree(
                            deps=remote_sub_deps,
                            resolution_stack=resolution_stack,
                            resolved_map=resolved_map,
                            constraints_by_address=constraints_by_address,
                            tags_cache=tags_cache,
                            cache_root=cache_root,
                            fetch_url_overrides=fetch_url_overrides,
                        )
                    finally:
                        resolution_stack.discard(dep.address)
            continue

        # Normal resolve
        resolution_stack.add(dep.address)
        try:
            override_url = (fetch_url_overrides or {}).get(dep.address)

            # Check if multiple constraints already (shouldn't happen on first visit, but defensive)
            if len(constraints_by_address[dep.address]) > 1:
                resolved_dep = _resolve_with_multiple_constraints(
                    address=dep.address,
                    alias=dep.alias,
                    constraints=constraints_by_address[dep.address],
                    tags_cache=tags_cache,
                    cache_root=cache_root,
                    fetch_url_override=override_url,
                )
            else:
                resolved_dep = resolve_remote_dependency(dep, cache_root=cache_root, fetch_url_override=override_url)

            resolved_map[dep.address] = resolved_dep

            # Recurse into sub-dependencies (remote only)
            if resolved_dep.manifest is not None and resolved_dep.manifest.dependencies:
                remote_sub_deps = [sub for sub in resolved_dep.manifest.dependencies if sub.path is None]
                if remote_sub_deps:
                    _resolve_transitive_tree(
                        deps=remote_sub_deps,
                        resolution_stack=resolution_stack,
                        resolved_map=resolved_map,
                        constraints_by_address=constraints_by_address,
                        tags_cache=tags_cache,
                        cache_root=cache_root,
                        fetch_url_overrides=fetch_url_overrides,
                    )
        finally:
            resolution_stack.discard(dep.address)


def resolve_all_dependencies(
    manifest: MthdsPackageManifest,
    package_root: Path,
    cache_root: Path | None = None,
    fetch_url_overrides: dict[str, str] | None = None,
) -> list[ResolvedDependency]:
    """Resolve all dependencies with transitive resolution for remote deps.

    Local path dependencies are resolved directly (no recursion into their sub-deps).
    Remote dependencies are resolved transitively with cycle detection and diamond
    constraint handling.

    Args:
        manifest: The consuming package's manifest.
        package_root: The root directory of the consuming package.
        cache_root: Override for the package cache root.
        fetch_url_overrides: Map of ``address`` to override clone URL (for tests).

    Returns:
        List of resolved dependencies (local + all transitive remote).

    Raises:
        DependencyResolveError: If any dependency fails to resolve.
        TransitiveDependencyError: If cycles or unsatisfiable diamonds are found.
    """
    # 1. Resolve local path deps (direct only, no recursion)
    local_resolved: list[ResolvedDependency] = []
    remote_deps: list[PackageDependency] = []

    for dep in manifest.dependencies:
        if dep.path is not None:
            resolved_dep = _resolve_local_dependency(dep, package_root)
            local_resolved.append(resolved_dep)
            local_export_count = len(resolved_dep.exported_pipe_codes) if resolved_dep.exported_pipe_codes is not None else "all"
            log.verbose(
                f"Resolved local dependency '{resolved_dep.alias}': {len(resolved_dep.mthds_files)} .mthds files, {local_export_count} exported pipes"
            )
        else:
            remote_deps.append(dep)

    # 2. Resolve remote deps transitively
    resolved_map: dict[str, ResolvedDependency] = {}
    constraints_by_address: dict[str, list[str]] = {}
    tags_cache: dict[str, list[tuple[Any, str]]] = {}
    resolution_stack: set[str] = set()

    if remote_deps:
        _resolve_transitive_tree(
            deps=remote_deps,
            resolution_stack=resolution_stack,
            resolved_map=resolved_map,
            constraints_by_address=constraints_by_address,
            tags_cache=tags_cache,
            cache_root=cache_root,
            fetch_url_overrides=fetch_url_overrides,
        )

    for resolved_dep in resolved_map.values():
        remote_export_count = len(resolved_dep.exported_pipe_codes) if resolved_dep.exported_pipe_codes is not None else "all"
        log.verbose(
            f"Resolved remote dependency '{resolved_dep.alias}': {len(resolved_dep.mthds_files)} .mthds files, {remote_export_count} exported pipes"
        )

    return local_resolved + list(resolved_map.values())
