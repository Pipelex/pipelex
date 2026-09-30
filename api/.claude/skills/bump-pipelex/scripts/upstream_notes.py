#!/usr/bin/env python3
"""Extract pipelex release notes for the versions a bump crosses.

Reads the sibling pipelex checkout's CHANGELOG.md and prints every released
section strictly after ``old_version`` up to and including ``new_version``.

Two boundaries this exists to get right:

- ``## [Unreleased]`` is never printed. It describes work that is not in the
  version being pinned, and quoting it in this repo's changelog is a factual
  error about what the upgrade contains.
- The old version's own section is excluded (it was already in effect) while
  the new version's is included.

Exits non-zero with an explanation when the checkout cannot answer -- most
often because it predates the version being pinned. Fall back to
``gh release view v<new> --repo Pipelex/pipelex`` in that case.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from packaging.version import InvalidVersion, Version

DEFAULT_CHANGELOG = Path(__file__).resolve().parents[4].parent / "pipelex" / "CHANGELOG.md"
HEADING = re.compile(r"^## \[v?(?P<version>\d+\.\d+\.\d+[^\]]*)\]")
UNRELEASED = re.compile(r"^## \[Unreleased\]", re.IGNORECASE)


def parse_version(raw: str) -> Version:
    """Parse a version string into a PEP 440 version.

    The upstream changelog carries prereleases ('0.18.0b4') alongside plain
    releases, so the ordering has to hold *among* prereleases as well as between
    a prerelease and the release it leads to: b3 < b4 < rc1 < 0.18.0. PEP 440 is
    what encodes that, and equality here is normalization-aware, so a section is
    matched by the version it denotes rather than by how it was spelled.
    """
    try:
        return Version(raw.strip())
    except InvalidVersion as exc:
        msg = f"Not a version this script can compare: {raw!r}"
        raise SystemExit(msg) from exc


def split_sections(text: str) -> list[tuple[str, str]]:
    """Return [(version, body)] for released sections, in file order."""
    sections: list[tuple[str, str]] = []
    current_version: str | None = None
    buffer: list[str] = []

    for line in text.splitlines():
        if UNRELEASED.match(line):
            if current_version is not None:
                sections.append((current_version, "\n".join(buffer).strip()))
            current_version, buffer = None, []
            continue
        match = HEADING.match(line)
        if match:
            if current_version is not None:
                sections.append((current_version, "\n".join(buffer).strip()))
            current_version, buffer = match.group("version"), [line]
            continue
        if current_version is not None:
            buffer.append(line)

    if current_version is not None:
        sections.append((current_version, "\n".join(buffer).strip()))
    return sections


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("old_version", help="the version currently pinned, excluded from the output")
    parser.add_argument("new_version", help="the version being pinned, included in the output")
    parser.add_argument(
        "--changelog",
        type=Path,
        default=DEFAULT_CHANGELOG,
        help=f"path to pipelex's CHANGELOG.md (default: {DEFAULT_CHANGELOG})",
    )
    args = parser.parse_args()

    if not args.changelog.is_file():
        print(
            f"No pipelex changelog at {args.changelog}.\n"
            f"Fall back to: gh release view v{args.new_version} --repo Pipelex/pipelex",
            file=sys.stderr,
        )
        return 2

    low = parse_version(args.old_version)
    high = parse_version(args.new_version)
    if low >= high:
        print(f"{args.new_version} is not newer than {args.old_version} -- nothing to digest.", file=sys.stderr)
        return 2

    sections = split_sections(args.changelog.read_text(encoding="utf-8"))
    known = {parse_version(version) for version, _ in sections}
    if high not in known:
        print(
            f"The checkout at {args.changelog} has no section for {args.new_version} -- "
            f"it likely predates that release.\n"
            f"Fall back to: gh release view v{args.new_version} --repo Pipelex/pipelex",
            file=sys.stderr,
        )
        return 3

    wanted = [(version, body) for version, body in sections if low < parse_version(version) <= high]
    if not wanted:
        print(f"No released sections between {args.old_version} (exclusive) and {args.new_version}.", file=sys.stderr)
        return 3

    print("\n\n".join(body for _, body in wanted))
    if low not in known:
        print(
            f"\nNote: no section for the old pin {args.old_version} in this checkout, "
            f"so the range may start earlier than the true gap.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
