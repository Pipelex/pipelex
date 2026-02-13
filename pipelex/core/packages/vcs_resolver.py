# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false
"""Git-based VCS operations for remote dependency fetching.

Maps package addresses to clone URLs, lists remote version tags, selects
versions via MVS, and clones at a specific tag.
"""

import subprocess  # noqa: S404
from pathlib import Path

from semantic_version import Version  # type: ignore[import-untyped]

from pipelex.core.packages.exceptions import VCSFetchError, VersionResolutionError
from pipelex.tools.misc.semver import parse_constraint, parse_version_tag, select_minimum_version


def address_to_clone_url(address: str) -> str:
    """Map a package address to a git clone URL.

    Prepends ``https://`` and appends ``.git`` (unless already present).

    Args:
        address: Package address, e.g. ``github.com/org/repo``.

    Returns:
        The HTTPS clone URL, e.g. ``https://github.com/org/repo.git``.
    """
    url = f"https://{address}"
    if not url.endswith(".git"):
        url = f"{url}.git"
    return url


def list_remote_version_tags(clone_url: str) -> list[tuple[Version, str]]:
    """List remote git tags that are valid semver versions.

    Runs ``git ls-remote --tags <url>`` and parses the output, filtering
    through :func:`parse_version_tag`. Dereferenced tag entries (``^{}``)
    are skipped.

    Args:
        clone_url: The git clone URL to query.

    Returns:
        List of ``(Version, original_tag_name)`` tuples.

    Raises:
        VCSFetchError: If the git command fails or git is not installed.
    """
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "ls-remote", "--tags", clone_url],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        msg = "git is not installed or not found on PATH"
        raise VCSFetchError(msg) from exc
    except subprocess.CalledProcessError as exc:
        msg = f"Failed to list remote tags from '{clone_url}': {exc.stderr.strip()}"
        raise VCSFetchError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        msg = f"Timed out listing remote tags from '{clone_url}'"
        raise VCSFetchError(msg) from exc

    version_tags: list[tuple[Version, str]] = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        ref = parts[1]

        # Skip dereferenced tags
        if ref.endswith("^{}"):
            continue

        # Extract tag name from refs/tags/...
        tag_name = ref.removeprefix("refs/tags/")
        version = parse_version_tag(tag_name)
        if version is not None:
            version_tags.append((version, tag_name))

    return version_tags


def resolve_version_from_tags(
    version_tags: list[tuple[Version, str]],
    version_constraint: str,
) -> tuple[Version, str]:
    """Select the minimum version matching a constraint from a list of tags.

    Uses :func:`parse_constraint` and :func:`select_minimum_version` from the
    semver module (MVS strategy).

    Args:
        version_tags: List of ``(Version, original_tag_name)`` tuples.
        version_constraint: The constraint string, e.g. ``^1.0.0``.

    Returns:
        Tuple of ``(selected_version, original_tag_name)``.

    Raises:
        VersionResolutionError: If no version satisfies the constraint.
    """
    if not version_tags:
        msg = f"No version tags available to satisfy constraint '{version_constraint}'"
        raise VersionResolutionError(msg)

    constraint = parse_constraint(version_constraint)
    versions = [entry[0] for entry in version_tags]
    selected = select_minimum_version(versions, constraint)

    if selected is None:
        available_str = ", ".join(str(entry[0]) for entry in sorted(version_tags))
        msg = f"No version satisfying '{version_constraint}' found among: {available_str}"
        raise VersionResolutionError(msg)

    # Find the corresponding tag name
    for ver, tag_name in version_tags:
        if ver == selected:
            return (selected, tag_name)

    # Unreachable since selected came from versions list, but satisfy type checker
    msg = f"Internal error: selected version {selected} not found in tag list"
    raise VersionResolutionError(msg)


def clone_at_version(clone_url: str, version_tag: str, destination: Path) -> None:
    """Clone a git repository at a specific tag with depth 1.

    Args:
        clone_url: The git clone URL.
        version_tag: The tag to check out (e.g. ``v1.0.0``).
        destination: The local directory to clone into.

    Raises:
        VCSFetchError: If the clone operation fails.
    """
    try:
        subprocess.run(  # noqa: S603
            ["git", "clone", "--depth", "1", "--branch", version_tag, clone_url, str(destination)],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        msg = "git is not installed or not found on PATH"
        raise VCSFetchError(msg) from exc
    except subprocess.CalledProcessError as exc:
        msg = f"Failed to clone '{clone_url}' at tag '{version_tag}': {exc.stderr.strip()}"
        raise VCSFetchError(msg) from exc
    except subprocess.TimeoutExpired as exc:
        msg = f"Timed out cloning '{clone_url}' at tag '{version_tag}'"
        raise VCSFetchError(msg) from exc
