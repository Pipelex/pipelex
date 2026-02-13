import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipelex import log
from pipelex.core.packages.discovery import MANIFEST_FILENAME, find_package_manifest
from pipelex.core.packages.exceptions import ManifestError, PackageCacheError, VCSFetchError, VersionResolutionError
from pipelex.core.packages.manifest import MthdsPackageManifest, PackageDependency
from pipelex.core.packages.package_cache import get_cached_package_path, is_cached, store_in_cache
from pipelex.core.packages.vcs_resolver import address_to_clone_url, clone_at_version, list_remote_version_tags, resolve_version_from_tags


class DependencyResolveError(Exception):
    """Raised when a dependency cannot be resolved."""


class ResolvedDependency(BaseModel):
    """A resolved local dependency with its manifest and file paths."""

    model_config = ConfigDict(frozen=True)

    alias: str
    manifest: MthdsPackageManifest | None
    package_root: Path
    mthds_files: list[Path]
    exported_pipe_codes: set[str]


def _collect_mthds_files(directory: Path) -> list[Path]:
    """Collect all .mthds files under a directory recursively.

    Args:
        directory: The directory to scan

    Returns:
        List of .mthds file paths found
    """
    return sorted(directory.rglob("*.mthds"))


def _determine_exported_pipes(manifest: MthdsPackageManifest | None) -> set[str]:
    """Determine which pipes are exported by a dependency.

    If a manifest with exports exists, use the exports. Otherwise all pipes are public.

    Args:
        manifest: The dependency's manifest (if any)

    Returns:
        Set of exported pipe codes. Empty set means "all public" (no manifest).
    """
    if manifest is None:
        # No manifest -> all pipes are public (empty set signals "all")
        return set()

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
        mthds_files = _collect_mthds_files(dep_dir)

        # Determine exported pipes
        exported_pipe_codes = _determine_exported_pipes(dep_manifest)

        resolved.append(
            ResolvedDependency(
                alias=dep.alias,
                manifest=dep_manifest,
                package_root=dep_dir,
                mthds_files=mthds_files,
                exported_pipe_codes=exported_pipe_codes,
            )
        )
        log.verbose(f"Resolved dependency '{dep.alias}': {len(mthds_files)} .mthds files, {len(exported_pipe_codes)} exported pipes")

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
    mthds_files = _collect_mthds_files(dep_dir)
    exported_pipe_codes = _determine_exported_pipes(dep_manifest)

    return ResolvedDependency(
        alias=dep.alias,
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
        return _build_resolved_from_dir(dep.alias, cached_path)

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
    return _build_resolved_from_dir(dep.alias, cached_path)


def _build_resolved_from_dir(alias: str, directory: Path) -> ResolvedDependency:
    """Build a ResolvedDependency from a package directory.

    Args:
        alias: The dependency alias.
        directory: The package directory (local or cached).

    Returns:
        The resolved dependency.
    """
    dep_manifest = _find_manifest_in_dir(directory)
    mthds_files = _collect_mthds_files(directory)
    exported_pipe_codes = _determine_exported_pipes(dep_manifest)

    return ResolvedDependency(
        alias=alias,
        manifest=dep_manifest,
        package_root=directory,
        mthds_files=mthds_files,
        exported_pipe_codes=exported_pipe_codes,
    )


def resolve_all_dependencies(
    manifest: MthdsPackageManifest,
    package_root: Path,
    cache_root: Path | None = None,
    fetch_url_overrides: dict[str, str] | None = None,
) -> list[ResolvedDependency]:
    """Resolve all dependencies: local path first, then VCS fetch for remote.

    For each dependency in the manifest:
    - If ``path`` is set: resolve locally (existing logic).
    - Otherwise: resolve via VCS fetch + cache.

    Args:
        manifest: The consuming package's manifest.
        package_root: The root directory of the consuming package.
        cache_root: Override for the package cache root.
        fetch_url_overrides: Map of ``address`` to override clone URL (for tests).

    Returns:
        List of resolved dependencies.

    Raises:
        DependencyResolveError: If any dependency fails to resolve.
    """
    resolved: list[ResolvedDependency] = []

    for dep in manifest.dependencies:
        if dep.path is not None:
            resolved_dep = _resolve_local_dependency(dep, package_root)
        else:
            override_url = (fetch_url_overrides or {}).get(dep.address)
            resolved_dep = resolve_remote_dependency(dep, cache_root=cache_root, fetch_url_override=override_url)

        resolved.append(resolved_dep)
        log.verbose(
            f"Resolved dependency '{resolved_dep.alias}': "
            f"{len(resolved_dep.mthds_files)} .mthds files, "
            f"{len(resolved_dep.exported_pipe_codes)} exported pipes"
        )

    return resolved
