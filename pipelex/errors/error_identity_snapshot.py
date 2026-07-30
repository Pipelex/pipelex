"""Snapshot of the wire-visible identity of every ``PipelexError`` subclass.

Every ``ErrorReport`` carries three identity fields — ``error_type``, ``title``
and ``type_uri`` (see :meth:`pipelex.base_exceptions.PipelexError.to_error_report`).
``error_type`` is the Python class name verbatim, with no indirection, and
external consumers branch on that string. Renaming an error class therefore
breaks them *silently*: their build stays green and the branch simply stops
matching, falling through to a generic error path.

``title`` and ``type_uri`` each have a declaration hatch (``_declared_title`` /
``_declared_type_uri``) precisely because they are presentation. ``error_type``,
the one field that is a machine contract, has none — so nothing in this repo
flagged a rename. This module closes that gap the cheap way: it renders the full
``(error_type, title, type_uri)`` set as a flat sorted table whose rendering is
committed to the repo, so a rename lands as a reviewable one-line-pair diff on a
single file at the moment it is made, instead of surfacing much later as a
fallthrough in a different repo.

Pure: :meth:`PipelexError.title` and :meth:`PipelexError.type_uri` read class
attributes and a module-level URL constant, so rendering needs no Pipelex
bootstrap.
"""

from __future__ import annotations

from typing import NamedTuple

from pipelex.errors.error_pages_generator import iter_pipelex_error_subclasses

# Column separator. Space-padded so the fields stay legible in a raw diff, and
# absent from every class name / type URI so a naive split round-trips.
SNAPSHOT_SEPARATOR = " | "

# Preamble written above the table. Explains what a diff here means to whoever
# is reviewing one, and names the command that regenerates the file.
_HEADER_LINES: tuple[str, ...] = (
    "# Wire identity of every PipelexError subclass: error_type | title | type_uri",
    "#",
    "# `error_type` is the Python class name, verbatim — base_exceptions.py builds it as",
    "# `type(self).__name__`. Consumers outside this repo switch on that string, so renaming",
    "# an error class is a wire break that no build anywhere catches: they stay green and",
    "# silently fall through to a generic branch. A diff in this file IS that wire break.",
    "#",
    "# Generated — do not hand-edit. Regenerate with `make generate-error-identity` (alias `make gei`).",
    "# Verified by tests/unit/pipelex/errors/test_error_identity_snapshot.py.",
)


class ErrorIdentityRow(NamedTuple):
    """One error class's wire-visible identity triple."""

    error_type: str
    title: str
    type_uri: str


def iter_error_identity_rows() -> list[ErrorIdentityRow]:
    """Return the identity triple of every discoverable ``PipelexError`` subclass, sorted.

    Population comes from :func:`iter_pipelex_error_subclasses`, which
    force-loads the deferred-import error modules and filters synthetic /
    fixture subclasses — the same set the generated docs pages and the
    ``type_uri`` uniqueness check agree on. Do not hand-roll a
    ``__subclasses__()`` walk here; see
    ``tests/unit/pipelex/errors/test_error_class_location_convention.py`` for why
    a naked walk is green for the wrong reason.

    Sorted by the triple itself so the rendering is stable across runs and
    independent of import order. Duplicate triples are not collapsed — two
    classes sharing a name would show as two identical lines rather than being
    silently merged (``test_pipelex_error_type_uri_uniqueness`` is what actually
    forbids that case).
    """
    rows = [ErrorIdentityRow(error_type=cls.__name__, title=cls.title(), type_uri=cls.type_uri()) for cls in iter_pipelex_error_subclasses()]
    return sorted(rows)


def render_error_identity_snapshot() -> str:
    """Render the committed snapshot text: the preamble, a blank line, then one row per class."""
    lines: list[str] = [*_HEADER_LINES, ""]
    for row in iter_error_identity_rows():
        lines.append(SNAPSHOT_SEPARATOR.join(row))
    return "\n".join(lines) + "\n"
