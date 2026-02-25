# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false
"""Thin typed wrapper around semantic_version for semver constraint evaluation.

Provides parsing, constraint matching, and Minimum Version Selection (MVS) for
the MTHDS package dependency system.

Note: semantic_version has no type stubs, so Pyright unknown-type checks are
disabled at file level for this wrapper module.
"""

from semantic_version import SimpleSpec, Version  # type: ignore[import-untyped]


class SemVerError(Exception):
    """Raised for semver parse failures."""


def parse_version(version_str: str) -> Version:
    """Parse a version string into a semantic_version.Version.

    Strips a leading 'v' prefix if present (common in git tags like v1.2.3).

    Args:
        version_str: The version string to parse (e.g. "1.2.3" or "v1.2.3").

    Returns:
        The parsed Version object.

    Raises:
        SemVerError: If the version string is not valid semver.
    """
    cleaned = version_str.lstrip("v") if version_str.startswith("v") else version_str
    try:
        return Version(cleaned)
    except ValueError as exc:
        msg = f"Invalid semver version: {version_str!r}"
        raise SemVerError(msg) from exc


def parse_constraint(constraint_str: str) -> SimpleSpec:
    """Parse a constraint string into a semantic_version.SimpleSpec.

    Args:
        constraint_str: The constraint string to parse (e.g. "^1.2.3", ">=1.0.0,<2.0.0").

    Returns:
        The parsed SimpleSpec object.

    Raises:
        SemVerError: If the constraint string is not valid.
    """
    try:
        return SimpleSpec(constraint_str)
    except ValueError as exc:
        msg = f"Invalid semver constraint: {constraint_str!r}"
        raise SemVerError(msg) from exc


def version_satisfies(version: Version, constraint: SimpleSpec) -> bool:
    """Check whether a version satisfies a constraint.

    Args:
        version: The version to check.
        constraint: The constraint to check against.

    Returns:
        True if the version satisfies the constraint.
    """
    result: bool = constraint.match(version)
    return result


def select_minimum_version(
    available_versions: list[Version],
    constraint: SimpleSpec,
) -> Version | None:
    """Select the minimum version that satisfies a constraint (MVS).

    Implements Go-style Minimum Version Selection for a single dependency:
    sorts versions ascending and returns the first match.

    Args:
        available_versions: The list of available versions.
        constraint: The constraint to satisfy.

    Returns:
        The minimum matching version, or None if no version matches.
    """
    for version in sorted(available_versions):
        if constraint.match(version):
            return version
    return None


def select_minimum_version_for_multiple_constraints(
    available_versions: list[Version],
    constraints: list[SimpleSpec],
) -> Version | None:
    """Select the minimum version that satisfies ALL constraints simultaneously.

    Used for transitive resolution when multiple packages depend on the same
    package with different constraints.

    Args:
        available_versions: The list of available versions.
        constraints: The list of constraints that must all be satisfied.

    Returns:
        The minimum version satisfying all constraints, or None if unsatisfiable.
    """
    for version in sorted(available_versions):
        if all(constraint.match(version) for constraint in constraints):
            return version
    return None


def parse_version_tag(tag: str) -> Version | None:
    """Parse a git tag into a Version, returning None if not a valid semver tag.

    Handles tags like "v1.2.3" and "1.2.3", and gracefully ignores non-semver
    tags like "release-20240101" or "latest".

    Args:
        tag: The git tag string.

    Returns:
        The parsed Version, or None if the tag is not valid semver.
    """
    try:
        return parse_version(tag)
    except SemVerError:
        return None
