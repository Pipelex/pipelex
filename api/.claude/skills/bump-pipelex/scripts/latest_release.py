#!/usr/bin/env python3
"""Resolve the latest pipelex release on PyPI from the release files themselves.

Prints the highest version that is a final release (a post-release counts, a
prerelease or a dev release does not) and still has a file that is not yanked.
With ``--pre``, prints instead every installable version newer than that one,
oldest first, for the user to pick from.

Why not ``info.version``: in the minutes after an upload, PyPI's JSON has been
seen listing the new version under ``releases`` while ``info.version`` still
named the previous one, in the same response. Reading ``info.version`` then
reports the pin as current when it is a release behind. The release files are
what the resolver installs from, so they are what this script ranks; when
``info.version`` disagrees, it says so on stderr.

Standard library only, so it runs with any ``python3`` before this checkout has
a virtualenv -- a fresh worktree has none until ``make li``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Any

PYPI_URL = "https://pypi.org/pypi/{package}/json"
PROJECT_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
TIMEOUT_SECONDS = 15

# The canonical PEP 440 spellings PyPI normalizes release keys to. Epochs and
# local versions never appear on PyPI for pipelex, so they are not handled.
VERSION = re.compile(r"^(?P<release>\d+(?:\.\d+)*)(?:(?P<pre_label>a|b|rc)(?P<pre_num>\d+))?(?:\.post(?P<post>\d+))?(?:\.dev(?P<dev>\d+))?$")
PRE_RANKS = {"a": 0, "b": 1, "rc": 2}
FINAL_RANK = 3

SortKey = tuple[tuple[int, ...], tuple[int, int], int, tuple[int, int]]


def sort_key(match: re.Match[str]) -> SortKey:
    """Order versions as PEP 440 does: 1.0.dev1 < 1.0a1 < 1.0rc1 < 1.0 < 1.0.post1."""
    parts = [int(part) for part in match.group("release").split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    pre_label = match.group("pre_label")
    post = match.group("post")
    dev = match.group("dev")
    if pre_label is not None:
        pre = (PRE_RANKS[pre_label], int(match.group("pre_num")))
    elif dev is not None and post is None:
        pre = (-1, 0)
    else:
        pre = (FINAL_RANK, 0)
    post_key = -1 if post is None else int(post)
    dev_key = (1, 0) if dev is None else (0, int(dev))
    return tuple(parts), pre, post_key, dev_key


def is_final(match: re.Match[str]) -> bool:
    return match.group("pre_label") is None and match.group("dev") is None


def is_installable(files: list[dict[str, Any]]) -> bool:
    """A version is installable when it has at least one file that is not yanked."""
    return any(not file_info.get("yanked", False) for file_info in files)


def fetch_metadata(package: str) -> dict[str, Any]:
    if PROJECT_NAME.match(package) is None:
        msg = f"Not a PyPI project name: {package!r}"
        raise SystemExit(msg)
    # The scheme is the fixed https of PYPI_URL, and the only interpolated part is a
    # validated project name, so the URL cannot be steered to file: or another host.
    url = PYPI_URL.format(package=package)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            payload: dict[str, Any] = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        msg = f"Could not read {url}: {exc}"
        raise SystemExit(msg) from exc
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package", default="pipelex", help="the PyPI project to ask about (default: pipelex)")
    parser.add_argument("--pre", action="store_true", help="list the installable versions newer than the latest final release")
    args = parser.parse_args()

    metadata = fetch_metadata(args.package)
    candidates: list[tuple[SortKey, str, bool]] = []
    for version, files in metadata.get("releases", {}).items():
        match = VERSION.match(version)
        if match is None:
            print(f"Skipping {version!r}: not a version spelling this script ranks.", file=sys.stderr)
            continue
        if is_installable(files):
            candidates.append((sort_key(match), version, is_final(match)))
    candidates.sort()

    finals = [(key, version) for key, version, final in candidates if final]
    if not finals:
        print(f"PyPI lists no installable final release of {args.package}.", file=sys.stderr)
        return 2
    latest_key, latest = finals[-1]

    if args.pre:
        newer = [version for key, version, _ in candidates if key > latest_key]
        if not newer:
            print(f"Nothing installable is newer than {latest}, the latest final release.", file=sys.stderr)
            return 0
        print("\n".join(newer))
        return 0

    print(latest)
    summary = metadata.get("info", {}).get("version")
    if summary != latest:
        print(
            f"Note: PyPI's info.version says {summary}, but the newest installable final release among the files is {latest}. "
            "Trust the files: the summary can lag an upload by some minutes, and it is not what the resolver installs from.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
