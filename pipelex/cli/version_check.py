"""Check for newer Pipelex versions on PyPI."""

import time
from pathlib import Path

import httpx

from pipelex.tools.misc.package_utils import get_package_version
from pipelex.tools.misc.semver import SemVerError, parse_version

PYPI_PACKAGE_NAME = "pipelex"
_COOLDOWN_SECONDS = 86400  # 24 hours


def _get_cache_path() -> Path:
    """Return the path to the version check cache file."""
    return Path.home() / ".pipelex" / ".version_check_cache"


def _is_check_due() -> bool:
    """Return True if enough time has passed since the last version check."""
    try:
        mtime = _get_cache_path().stat().st_mtime
        return (time.time() - mtime) > _COOLDOWN_SECONDS
    except OSError:
        return True


def _touch_cache() -> None:
    """Update the cache file timestamp to record a successful check."""
    cache_path = _get_cache_path()
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.touch()
    except OSError:
        pass


def _get_latest_pypi_version() -> str | None:
    """Fetch the latest version of Pipelex from PyPI.

    Returns:
        The latest version string, or None if the check fails.
    """
    url = f"https://pypi.org/pypi/{PYPI_PACKAGE_NAME}/json"
    try:
        response = httpx.get(url, timeout=3, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
        return str(data["info"]["version"])
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def check_for_update() -> str | None:
    """Check if a newer version of Pipelex is available on PyPI.

    Checks at most once every 24 hours to avoid slowing down every CLI invocation.

    Returns:
        The latest version string if an update is available, or None if up to date or check fails.
    """
    if not _is_check_due():
        return None

    latest_version = _get_latest_pypi_version()
    _touch_cache()

    if latest_version is None:
        return None

    current_version = get_package_version()
    try:
        current = parse_version(current_version)
        latest = parse_version(latest_version)
    except SemVerError:
        return None

    if latest > current:
        return latest_version
    return None
