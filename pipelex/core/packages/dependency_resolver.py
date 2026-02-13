from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipelex import log
from pipelex.core.packages.discovery import MANIFEST_FILENAME, find_package_manifest
from pipelex.core.packages.exceptions import ManifestError
from pipelex.core.packages.manifest import MthdsPackageManifest


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
