"""How every document engine shows a layout tree's values, so a document reads the same whichever engine printed it.

The built-in PDF engine and the engines of the Pipelex document generation plugin write the same layout tree
(`layout_tree.py`) in different formats, and they show its values through these functions rather than through
rules of their own:

- `display_scalar` writes a scalar as text: blank for nothing, Yes or No, numbers plainly, dates and times in
  ISO order with the UTC offset they state;
- `is_numeric_column` says whether a table's column holds numbers only, which an engine aligns right;
- `markdown_as_html` converts a `MarkdownBlock` to an HTML fragment with the one parser Pipelex reads Markdown
  with, for an engine that writes HTML.

This module is part of the document engine contract (`pipelex/plugins/contract.py`), and it imports no engine,
so a plugin's engine can use it without loading ReportLab.
"""

import datetime

from pipelex.cogt.doc_gen.layout_tree import LayoutScalar
from pipelex.tools.markdown.markdown_parser import render_markdown_as_html


def display_scalar(*, value: LayoutScalar) -> str:
    """A scalar as the document prints it: blank for nothing, Yes or No, numbers plainly, dates and times in ISO order.

    A time of day prints to the minute, with the UTC offset the value states, if any.
    """
    match value:
        case None:
            return ""
        case bool():
            return "Yes" if value else "No"
        case int():
            return str(value)
        case float():
            if value.is_integer():
                return str(int(value))
            return format(value, ".15g")
        case datetime.datetime():
            return value.strftime("%Y-%m-%d %H:%M") + _utc_offset_suffix(value=value)
        case datetime.date():
            return value.isoformat()
        case datetime.time():
            return value.strftime("%H:%M") + _utc_offset_suffix(value=value)
        case str():
            return value


def _utc_offset_suffix(*, value: datetime.datetime | datetime.time) -> str:
    """The UTC offset a value states, as ' UTC' or ' +02:00', or nothing for a value that states none."""
    offset = value.utcoffset()
    if offset is None:
        return ""
    total_minutes = int(offset.total_seconds()) // 60
    if total_minutes == 0:
        return " UTC"
    sign = "+" if total_minutes > 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f" {sign}{hours:02d}:{minutes:02d}"


def is_numeric_column(*, values: list[LayoutScalar]) -> bool:
    """Whether a column holds numbers only, blanks aside, and at least one: such a column is aligned right."""
    present = [value for value in values if value is not None]
    return bool(present) and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in present)


def markdown_as_html(*, markdown: str) -> str:
    """Markdown as an HTML fragment, parsed as the `markdown` filter, the `Markdown` concept and the built-in engine parse it.

    The parser reads CommonMark with tables and strikethrough; raw HTML in the source comes out escaped, so it
    shows as text rather than entering the document; and only a URL with a scheme becomes a link, so `README.md`
    or `www.example.com` stays text.

    A conversion is charged to the budget of the template render running at the time, so one an engine makes from
    its own code, outside any template render, is charged to none: the engine bounds what it converts and prints.
    """
    return render_markdown_as_html(markdown)
