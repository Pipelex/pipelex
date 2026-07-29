"""Gate on the committed ``(error_type, title, type_uri)`` snapshot.

``error_type`` is the Python class name with no indirection, and consumers
outside this repo branch on that string, so renaming an error class breaks them
*silently* — their build stays green and the branch stops matching. Nothing in
this repo flagged that. This test does: it re-renders the identity set and
compares it to the committed file, so a rename cannot land without a reviewable
diff on ``tests/data/errors/error_identity.txt``.

The set comes from ``iter_pipelex_error_subclasses()`` rather than a naked
``__subclasses__()`` walk — see ``test_error_class_location_convention.py`` for
why the naked walk is green for the wrong reason.
"""

from __future__ import annotations

from difflib import unified_diff
from pathlib import Path

import pipelex
from pipelex.cli.dev_cli.commands.generate_error_identity_cmd import ERROR_IDENTITY_PATH
from pipelex.errors.error_identity_snapshot import SNAPSHOT_SEPARATOR, iter_error_identity_rows, render_error_identity_snapshot

_REPO_ROOT: Path = Path(pipelex.__file__).resolve().parent.parent
_SNAPSHOT_FILE: Path = _REPO_ROOT / ERROR_IDENTITY_PATH


class TestErrorIdentitySnapshot:
    def test_enumerated_identity_set_is_not_empty(self) -> None:
        """Anti-vacuity: the discovery helper actually found error classes.

        Deliberately NOT parametrized over the class list. A parametrized body
        cannot carry this assertion — pytest reports ``got empty parameter set``
        and exits 0 when the list is empty, so the guard would be unreachable
        exactly when it matters.
        """
        rows = iter_error_identity_rows()
        assert rows, "No PipelexError subclasses discovered — the snapshot would compare two empty sets and pass vacuously."

        error_types = {row.error_type for row in rows}
        assert "PipelexError" in error_types, "The root error class must always appear in the identity set."

    def test_no_identity_field_contains_the_column_separator(self) -> None:
        """The rendering is only unambiguous while no field contains the separator."""
        offenders = [row for row in iter_error_identity_rows() if any(SNAPSHOT_SEPARATOR in field for field in row)]
        if offenders:
            lines = [
                f"Identity fields contain the column separator {SNAPSHOT_SEPARATOR!r}, which makes the snapshot ambiguous:",
                "",
                *(f"  - {row.error_type}: {row!r}" for row in offenders),
                "",
                "Rename the class or curate a _declared_title without the separator.",
            ]
            raise AssertionError("\n".join(lines))

    def test_committed_snapshot_matches_the_live_error_classes(self) -> None:
        """The committed snapshot is the current identity set — regenerate on any diff."""
        expected = render_error_identity_snapshot()

        assert _SNAPSHOT_FILE.exists(), f"Missing snapshot file {_SNAPSHOT_FILE} — run `make gei` to generate it."

        existing = _SNAPSHOT_FILE.read_text(encoding="utf-8")
        if existing == expected:
            return

        diff = list(
            unified_diff(
                existing.splitlines(keepends=True),
                expected.splitlines(keepends=True),
                fromfile="committed (on disk)",
                tofile="live (rendered from the error classes)",
                lineterm="",
            )
        )
        lines = [
            "The committed error-identity snapshot is out of date.",
            "",
            "A diff on `error_type` is a WIRE BREAK: consumers outside this repo switch on that",
            "string and fall through silently when it changes. Confirm the rename is intended and",
            "that the consumers are updated in the cross-repo sweep, then run `make gei`.",
            "",
            *(line.rstrip("\n") for line in diff),
        ]
        raise AssertionError("\n".join(lines))
