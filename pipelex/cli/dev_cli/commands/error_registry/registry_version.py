"""The version Pipelex's error registry is published under: Pipelex's own version, written as SemVer.

Pipelex's version, the ``[project].version`` of ``pyproject.toml``, is a PEP 440 version: ``X.Y.Z`` for a
release, and ``X.Y.Z`` followed by ``a``, ``b`` or ``rc`` and a number for a pre-release, such as ``0.88.0rc1``.
The MTHDS registry format writes a registry's version as SemVer, a pre-release following a hyphen, and refuses
``0.88.0rc1``. So the registry writes a release's number as it is, and a pre-release's with its phase and its
number as two dot-separated identifiers after a hyphen: ``0.88.0a1`` is ``0.88.0-a.1``, ``0.88.0b2`` is
``0.88.0-b.2`` and ``0.88.0rc1`` is ``0.88.0-rc.1``. SemVer then orders them as PEP 440 does: ``a`` before ``b``
before ``rc``, ``rc.2`` before ``rc.10`` because a numeric identifier is compared as a number, and every
pre-release before its release.

The module needs nothing but the standard library, so that the release workflow runs it on a bare runner, without
the repository's environment, to learn the version the registry's snapshot must carry:

    python3 -I pipelex/cli/dev_cli/commands/error_registry/registry_version.py 0.88.0rc1
"""

from __future__ import annotations

import re
import sys

_PEP440_VERSION_REGEX = re.compile(r"^(?P<release>\d+\.\d+\.\d+)(?:(?P<phase>a|b|rc)(?P<number>\d+))?$")


def registry_version_of(*, package_version: str) -> str:
    """The registry's version for a Pipelex version: a release's number as it is, a pre-release's in SemVer form.

    Raises:
        ValueError: When the version is neither ``X.Y.Z`` nor ``X.Y.Z`` followed by ``a``, ``b`` or ``rc`` and a
            number, the only forms Pipelex releases under.
    """
    match = _PEP440_VERSION_REGEX.fullmatch(package_version)
    if match is None:
        msg = (
            f"the version '{package_version}' is neither a release, X.Y.Z, nor a pre-release, X.Y.Z followed by a, b or rc "
            "and a number, so the error registry cannot be published under it"
        )
        raise ValueError(msg)
    phase = match.group("phase")
    if phase is None:
        return match.group("release")
    return f"{match.group('release')}-{phase}.{match.group('number')}"


def main() -> None:
    """Print the registry's version for the Pipelex version given as the only argument, or exit with 2."""
    arguments = sys.argv[1:]
    if len(arguments) != 1:
        print("usage: registry_version.py <pipelex version>", file=sys.stderr)
        sys.exit(2)
    try:
        print(registry_version_of(package_version=arguments[0]))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
