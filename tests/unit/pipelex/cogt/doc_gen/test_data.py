import datetime
from typing import ClassVar

from pipelex.cogt.doc_gen.layout_tree import LayoutScalar


class LayoutDisplayTestData:
    """Each scalar case: (value, its text). Each numeric column case: (topic, values, whether the column is numeric)."""

    SCALAR_CASES: ClassVar[list[tuple[LayoutScalar, str]]] = [
        (None, ""),
        (True, "Yes"),
        (False, "No"),
        (42, "42"),
        (2.0, "2"),
        (2.5, "2.5"),
        (0.1 + 0.2, "0.3"),
        (datetime.date(2026, 9, 29), "2026-09-29"),
        (datetime.datetime(2026, 9, 29, 14, 5, 59), "2026-09-29 14:05"),
        (datetime.time(9, 7, 30), "09:07"),
        (datetime.datetime(2026, 9, 29, 14, 5, tzinfo=datetime.UTC), "2026-09-29 14:05 UTC"),
        (datetime.datetime(2026, 9, 29, 14, 5, tzinfo=datetime.timezone(datetime.timedelta(hours=2))), "2026-09-29 14:05 +02:00"),
        (datetime.time(9, 7, tzinfo=datetime.timezone(datetime.timedelta(hours=-5, minutes=-30))), "09:07 -05:30"),
        ("As written", "As written"),
    ]

    NUMERIC_COLUMN_CASES: ClassVar[list[tuple[str, list[LayoutScalar], bool]]] = [
        ("integers and floats", [1, 2.5, 3], True),
        ("numbers with blanks", [None, 4, None], True),
        ("no rows", [], False),
        ("blanks only", [None, None], False),
        ("booleans", [True, False], False),
        ("a boolean among numbers", [1, True], False),
        ("a text among numbers", [1, "2"], False),
        ("dates", [datetime.date(2026, 9, 29)], False),
    ]


class FormattedMarkdownTestData:
    """Markdown texts the formatting tests read, and what each formats into."""

    # A header of three thousand columns over three hundred one-character rows: nine hundred thousand cells, which the
    # table rule pads every row to, out of about ten kilobytes of text.
    PADDED_TABLE: ClassVar[str] = "|" + "a|" * 3000 + "\n|" + "-|" * 3000 + "\n" + "|a\n" * 300

    # A reference link used four thousand times, whose twenty-thousand-character address an engine printing a link's
    # address beside its text prints at every use: its text alone fits a budget, what it formats into does not.
    REUSED_REFERENCE: ClassVar[str] = "[a][r] " * 4000 + "\n\n[r]: https://example.com/" + "y" * 20000

    # A report section repeated into about thirty thousand characters: an ordinary long text, well within one budget.
    LONG_REPORT: ClassVar[str] = "## Findings\n\nSome *text* with a [link](https://a.co), `code` and more.\n\n- one\n- two\n\n" * 300

    # The text an invoice's notes hold, and its plain text.
    NOTES: ClassVar[str] = "Payment by **bank transfer** within 30 days.\n\n- *Late* fees apply\n- IBAN on request"
    NOTES_PLAIN_TEXT: ClassVar[str] = "Payment by bank transfer within 30 days.\n• Late fees apply\n• IBAN on request"

    # Every kind of block, and its plain text: list items indented by depth, a later paragraph of an item indented
    # under its marker, table cells separated by tabs, a code block as written, and the rule left out.
    EVERY_BLOCK: ClassVar[str] = (
        "# Report\n\n"
        "Some **bold** text, a [link](https://pipelex.com) and `code`.  \nOn its own line.\n\n"
        "- one\n  - two\n\n  more about one\n\n"
        "3. three\n4. four\n\n"
        "> Quoted *words*\n\n"
        "---\n\n"
        "| Item | Qty |\n| --- | --: |\n| Tea | 2 |\n\n"
        "```\nprint('x')\n```\n"
    )
    EVERY_BLOCK_PLAIN_TEXT: ClassVar[str] = (
        "Report\n"
        "Some bold text, a link and code.\nOn its own line.\n"
        "• one\n  – two\n  more about one\n"
        "3. three\n4. four\n"
        "Quoted words\n"
        "Item\tQty\nTea\t2\n"
        "print('x')"
    )
