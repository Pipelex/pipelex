"""Snapshot of the wire-visible identity of every ``PipelexError`` subclass: its name and its code.

Every problem carries the registry ``code`` its error resolved to, and the operator's view carries the Python
class name verbatim as ``diagnostics.error_class``, which operators' tooling may branch on. Renaming an error class
therefore breaks it *silently*, and so does changing the code a class raises: its build stays green and the branch
simply stops matching, falling through to a generic error path.

This module closes that gap the cheap way: it renders every class's name and code declaration (the code, the
set its raise sites choose from, the cause it takes its code from, or that it is abstract, as
:func:`~pipelex.errors.error_code_declaration.describe_error_code_declaration` reads it) as a flat sorted table
whose rendering is committed to the repo, so a rename or a change of code lands as a reviewable diff on a single
file at the moment it is made, instead of surfacing much later as a fallthrough in a different repo.

Pure: a declaration is a class attribute, so rendering needs no Pipelex bootstrap.
"""

from __future__ import annotations

from typing import NamedTuple

from pipelex.errors.error_class_discovery import iter_pipelex_error_subclasses
from pipelex.errors.error_code_declaration import describe_error_code_declaration

# Column separator. Space-padded so the fields stay legible in a raw diff, and
# absent from every class name and declaration so a naive split round-trips.
SNAPSHOT_SEPARATOR = " | "

# Preamble written above the table. Explains what a diff here means to whoever
# is reviewing one, and names the command that regenerates the file.
_HEADER_LINES: tuple[str, ...] = (
    "# Wire identity of every PipelexError subclass: error_type | code declaration",
    "#",
    "# `error_type` is the Python class name, verbatim — base_exceptions.py builds it as",
    "# `type(self).__name__`. Consumers outside this repo switch on that string, so renaming",
    "# an error class is a wire break that no build anywhere catches: they stay green and",
    "# silently fall through to a generic branch. The declaration is the registry code the",
    "# class raises, the set its raise sites choose from, the cause it takes its code from,",
    "# or `abstract`; a change to it changes what every reader of the code is told to do.",
    "# A diff in this file IS that wire change.",
    "#",
    "# Generated — do not hand-edit. Regenerate with `make generate-error-identity` (alias `make gei`).",
    "# Verified by tests/unit/pipelex/errors/test_error_identity_snapshot.py.",
)


class ErrorIdentityRow(NamedTuple):
    """One error class's wire-visible identity: its name and its code declaration."""

    error_type: str
    code_declaration: str


def iter_error_identity_rows() -> list[ErrorIdentityRow]:
    """Return the identity of every discoverable ``PipelexError`` subclass, sorted.

    Population comes from :func:`iter_pipelex_error_subclasses`, which
    force-loads the deferred-import error modules and filters synthetic /
    fixture subclasses. Do not hand-roll a ``__subclasses__()`` walk here; see
    ``tests/unit/pipelex/errors/test_error_class_location_convention.py`` for why
    a naked walk is green for the wrong reason.

    Sorted by the row itself so the rendering is stable across runs and
    independent of import order. Duplicate rows are not collapsed — two
    classes sharing a name would show as two lines rather than being
    silently merged (``test_pipelex_error_class_name_uniqueness`` is what actually
    forbids that case).
    """
    rows = [
        ErrorIdentityRow(error_type=cls.__name__, code_declaration=describe_error_code_declaration(cls.error_code))
        for cls in iter_pipelex_error_subclasses()
    ]
    return sorted(rows)


def render_error_identity_snapshot() -> str:
    """Render the committed snapshot text: the preamble, a blank line, then one row per class."""
    lines: list[str] = [*_HEADER_LINES, ""]
    for row in iter_error_identity_rows():
        lines.append(SNAPSHOT_SEPARATOR.join(row))
    return "\n".join(lines) + "\n"
