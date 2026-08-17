"""Reading a TOML document as a set of addressable paths and values.

The fingerprint projects a *model tree*; this projects a *document*. The two use the same dotted
addressing so a check can compare them, but they are not the same thing and the difference is
load-bearing: a document carries the concrete keys a user chose beneath an open node, where the
fingerprint records only the value schema under a `*`, and a document omits every optional key
that is not set.

Used by the checks that compare a migrated document against the one the new schema expects.
"""

from typing import Any, cast

from pipelex.migration.fingerprint import PATH_SEPARATOR
from pipelex.suggested_fix import WILDCARD_SEGMENT


def document_paths(*, document: dict[str, Any]) -> set[str]:
    """Every addressable path in a document, tables and leaves alike.

    Tables are included as paths of their own, not only their leaves, so that deleting a whole
    section is visible as the removal of the section rather than only of its contents.
    """
    return set(flatten_document(document=document))


def flatten_document(*, document: dict[str, Any]) -> dict[str, Any]:
    """A document as a flat path-to-value mapping, table paths included with value `None`.

    An array of tables is recorded as a terminal path and not descended into, matching the
    fingerprint: no `table_path` segment syntax reaches inside one, so nothing can address it.
    """
    flattened: dict[str, Any] = {}
    _flatten_into(mapping=document, prefix=(), flattened=flattened)
    return flattened


def _flatten_into(*, mapping: dict[str, Any], prefix: tuple[str, ...], flattened: dict[str, Any]) -> None:
    for key, value in mapping.items():
        path = (*prefix, str(key))
        dotted = PATH_SEPARATOR.join(path)
        if isinstance(value, dict):
            flattened[dotted] = None
            _flatten_into(mapping=cast("dict[str, Any]", value), prefix=path, flattened=flattened)
            continue
        flattened[dotted] = value


def document_carries_path(*, paths: set[str], pattern: str) -> bool:
    """Whether a document has anything at a schema path, `*` standing for one key of an open node.

    A schema path is not a document path: beneath an open mapping the schema says `levels.*` while
    the document says `levels.my_package`, and a literal lookup would answer "no" for every file
    that has ever set one.
    """
    if WILDCARD_SEGMENT not in pattern:
        return pattern in paths
    return any(path_matches_pattern(path=path, pattern=pattern) for path in paths)


def path_matches_pattern(*, path: str, pattern: str) -> bool:
    """Whether one document path is the one a schema path names.

    Each `*` matches exactly one segment, which is what it means in the fingerprint and in an
    operation alike — never a whole subtree. This is the single definition of that rule; everything
    that compares a document against a schema path or an operation's target reads it, so the two
    directions of the question cannot come to different answers.
    """
    expected = pattern.split(PATH_SEPARATOR)
    segments = path.split(PATH_SEPARATOR)
    if len(segments) != len(expected):
        return False
    return _segments_match(segments=segments, expected=expected)


def path_is_at_or_under_pattern(*, path: str, pattern: str) -> bool:
    """Whether a document path is the one a pattern names, or sits inside it.

    An operation that deletes or renames a table takes the whole subtree with it, so a pattern
    naming that table answers for every path beneath it too.
    """
    expected = pattern.split(PATH_SEPARATOR)
    segments = path.split(PATH_SEPARATOR)
    if len(segments) < len(expected):
        return False
    return _segments_match(segments=segments[: len(expected)], expected=expected)


def _segments_match(*, segments: list[str], expected: list[str]) -> bool:
    return all(wanted in {WILDCARD_SEGMENT, found} for wanted, found in zip(expected, segments, strict=True))
