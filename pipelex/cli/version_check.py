"""Check for newer Pipelex versions on PyPI."""

import httpx

from pipelex.tools.misc.package_utils import get_package_version
from pipelex.tools.misc.semver import SemVerError, parse_version

PYPI_PACKAGE_NAME = "pipelex"


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

    Returns:
        The latest version string if an update is available, or None if up to date or check fails.
    """
    latest_version = _get_latest_pypi_version()
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
