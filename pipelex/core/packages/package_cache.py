"""Local package cache for fetched remote MTHDS dependencies.

Cache layout: ``{cache_root}/{address}/{version}/``
(e.g. ``~/.mthds/packages/github.com/org/repo/1.0.0/``).

Uses a staging directory + atomic rename for safe writes.
"""

import shutil
from pathlib import Path

from pipelex.core.packages.exceptions import PackageCacheError


def get_default_cache_root() -> Path:
    """Return the default cache root directory.

    Returns:
        ``~/.mthds/packages``
    """
    return Path.home() / ".mthds" / "packages"


def get_cached_package_path(
    address: str,
    version: str,
    cache_root: Path | None = None,
) -> Path:
    """Compute the cache path for a package version.

    Args:
        address: Package address, e.g. ``github.com/org/repo``.
        version: Resolved version string, e.g. ``1.0.0``.
        cache_root: Override for the cache root directory.

    Returns:
        The directory path where this package version would be cached.
    """
    root = cache_root or get_default_cache_root()
    return root / address / version


def is_cached(
    address: str,
    version: str,
    cache_root: Path | None = None,
) -> bool:
    """Check whether a package version exists in the cache.

    A directory is considered cached if it exists and is non-empty.

    Args:
        address: Package address.
        version: Resolved version string.
        cache_root: Override for the cache root directory.

    Returns:
        True if the cached directory exists and is non-empty.
    """
    pkg_path = get_cached_package_path(address, version, cache_root)
    if not pkg_path.is_dir():
        return False
    return any(pkg_path.iterdir())


def store_in_cache(
    source_dir: Path,
    address: str,
    version: str,
    cache_root: Path | None = None,
) -> Path:
    """Copy a package directory into the cache.

    Uses a staging directory (``{path}.staging``) and an atomic rename for
    safe writes. Removes the ``.git/`` subdirectory from the cached copy.

    Args:
        source_dir: The directory to copy from (e.g. a fresh clone).
        address: Package address.
        version: Resolved version string.
        cache_root: Override for the cache root directory.

    Returns:
        The final cache path.

    Raises:
        PackageCacheError: If copying or renaming fails.
    """
    final_path = get_cached_package_path(address, version, cache_root)
    staging_path = final_path.parent / f"{final_path.name}.staging"

    try:
        # Clean up any leftover staging dir
        if staging_path.exists():
            shutil.rmtree(staging_path)

        # Copy source into staging
        shutil.copytree(source_dir, staging_path)

        # Remove .git/ from the staged copy
        git_dir = staging_path / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir)

        # Ensure parent exists and perform atomic rename
        final_path.parent.mkdir(parents=True, exist_ok=True)
        if final_path.exists():
            shutil.rmtree(final_path)
        staging_path.rename(final_path)

    except OSError as exc:
        # Clean up staging on failure
        if staging_path.exists():
            shutil.rmtree(staging_path, ignore_errors=True)
        msg = f"Failed to store package '{address}@{version}' in cache: {exc}"
        raise PackageCacheError(msg) from exc

    return final_path


def remove_cached_package(
    address: str,
    version: str,
    cache_root: Path | None = None,
) -> bool:
    """Remove a cached package version.

    Args:
        address: Package address.
        version: Resolved version string.
        cache_root: Override for the cache root directory.

    Returns:
        True if the directory existed and was removed, False otherwise.
    """
    pkg_path = get_cached_package_path(address, version, cache_root)
    if not pkg_path.exists():
        return False
    shutil.rmtree(pkg_path)
    return True
