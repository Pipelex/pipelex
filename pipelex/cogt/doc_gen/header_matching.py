"""How a table's column headers and a template's names find the fields of a record, the one rule every reader and writer applies.

Names are compared ignoring case, spaces, dots and underscores (`field_key`), so `InvoiceCustomerName` and a dotted name
find the same field, and a `Unit price` header binds `unit_price`. A header that matches several fields is ambiguous,
which the caller refuses, naming the header by its position.

The rule is public because both sides of a spreadsheet use it: `PipeStructure` reads a Table's columns into records with
it (`pipelex.tools.tabular`), and a document engine's fill writes records into a Table's columns with it, so the reader
and the writer can never disagree about which column holds which field. It is part of the plugin contract: an engine
imports it from here rather than keeping a copy of its own.
"""

import re
from collections.abc import Iterable, Mapping

_SEPARATORS = re.compile(r"[\s._]")


def field_key(name: str) -> str:
    """The form in which a template's names, a column header and a field path are compared: no spaces, dots or underscores, lowercased."""
    return _SEPARATORS.sub("", name).lower()


def column_fields(*, headers: Mapping[int, str], field_names: Iterable[str]) -> dict[int, list[str]]:
    """The fields each column's header matches, by column index: one binds the column, several are ambiguous.

    A column whose header matches no field has no entry.

    Args:
        headers: Each column's header, by the column's index, as the caller numbers its columns.
        field_names: The names of the record's fields.

    Returns:
        The fields each matching header matches, sorted, by column index.
    """
    fields_by_key: dict[str, list[str]] = {}
    for field_name in field_names:
        fields_by_key.setdefault(field_key(field_name), []).append(field_name)
    matched: dict[int, list[str]] = {}
    for column_index, header in headers.items():
        candidates = fields_by_key.get(field_key(header))
        if candidates:
            matched[column_index] = sorted(candidates)
    return matched
