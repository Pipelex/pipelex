"""The foreign-raise check: our own code raises no class outside the ``PipelexError`` root that a reader can see.

``pipelex/errors/foreign_raises.py`` scans the package and the runner, ``api/pipelex_api``, and allows by their
shape the raises that are right: inside pydantic validators, abstract methods, data-model dunders, the framework
carriers and the developer tooling. Every other foreign raise is listed, with its disposition, in
``tests/data/errors/foreign_raises.txt``. This test fails on a foreign raise the file does not list, which is
a new raise to code under the root (or, when it is a genuine invariant or carrier, to list with its
disposition), and on a listed one that is gone, so the file never keeps a stale line.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pipelex
from pipelex.errors.foreign_raises import ForeignRaiseSite, collect_root_error_class_names, is_exempt_path, iter_foreign_raise_sites

_PACKAGE_ROOT: Path = Path(pipelex.__file__).resolve().parent
_REPO_ROOT: Path = _PACKAGE_ROOT.parent
_SOURCE_ROOTS: tuple[Path, ...] = (_PACKAGE_ROOT, _REPO_ROOT / "api" / "pipelex_api")
_BASELINE_FILE: Path = _REPO_ROOT / "tests" / "data" / "errors" / "foreign_raises.txt"
_SEPARATOR = " | "

# Why a listed foreign raise is right.
_DISPOSITIONS: frozenset[str] = frozenset(
    {
        # A builtin raised only on a bug of ours, which a boundary reports as runtime.unexpected.
        "invariant",
        # A builtin raised in a helper only pydantic validators call, which pydantic wraps.
        "validator",
        # A private class caught in the module that defines it, which no reader sees.
        "private",
        # A class a library expects by type that the scan cannot recognise by its name alone.
        "carrier",
        # Developer or release code outside the exempt directories, which only the development CLI calls.
        "tooling",
        # A builtin raised in a module that must import nothing of Pipelex, which its every caller catches by type.
        "caught",
    }
)


def _sources() -> list[tuple[Path, str]]:
    sources: list[tuple[Path, str]] = []
    for root in _SOURCE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            sources.append((path, path.read_text(encoding="utf-8")))
    return sources


def _live_sites() -> list[ForeignRaiseSite]:
    sources = _sources()
    root_names = collect_root_error_class_names(sources=sources)
    sites: list[ForeignRaiseSite] = []
    for path, source in sources:
        relative = path.relative_to(_REPO_ROOT)
        if is_exempt_path(relative_parts=relative.parts):
            continue
        sites.extend(iter_foreign_raise_sites(path=str(relative), source=source, root_names=root_names))
    return sites


def _baseline() -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for raw_line in _BASELINE_FILE.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.startswith("#"):
            continue
        fields = raw_line.split(_SEPARATOR)
        assert len(fields) == 4, f"A line of {_BASELINE_FILE.name} has {len(fields)} fields, not 4: {raw_line!r}"
        path, function, exception, disposition = fields
        rows.append((path, function, exception, disposition))
    return rows


class TestForeignRaises:
    def test_the_scan_reads_the_sources(self) -> None:
        """Anti-vacuity: the scan read the package and found the root's family."""
        sources = _sources()
        assert sources
        root_names = collect_root_error_class_names(sources=sources)
        assert {"PipelexError", "PipelexUnexpectedError", "CogtError"} <= root_names

    def test_every_listed_disposition_is_known(self) -> None:
        unknown = sorted({row[3] for row in _baseline()} - _DISPOSITIONS)
        assert not unknown, f"{_BASELINE_FILE.name} uses dispositions this check does not know: {unknown}; use one of {sorted(_DISPOSITIONS)}"

    def test_every_foreign_raise_is_listed_and_every_listed_one_exists(self) -> None:
        live = Counter(site.key for site in _live_sites())
        listed = Counter((path, function, exception) for path, function, exception, _disposition in _baseline())
        unlisted = live - listed
        stale = listed - live
        lines: list[str] = []
        if unlisted:
            where = {site.key: site.line for site in _live_sites()}
            lines.extend(
                [
                    "These raises construct a class outside the PipelexError root and are not listed:",
                    "",
                    *(
                        f"  - {path}:{where[path, function, exception]} ({function}) raises {exception}"
                        for path, function, exception in sorted(unlisted)
                    ),
                    "",
                    "A reader that sees one gets no code: raise a coded PipelexError subclass instead. When the raise is",
                    f"right as it is, list it in tests/data/errors/foreign_raises.txt with one of {sorted(_DISPOSITIONS)}.",
                ]
            )
        if stale:
            lines.extend(
                [
                    "",
                    "These listed foreign raises are gone; remove their lines from tests/data/errors/foreign_raises.txt:",
                    "",
                    *(f"  - {_SEPARATOR.join(key)}" for key in sorted(stale)),
                ]
            )
        assert not lines, "\n".join(lines)
