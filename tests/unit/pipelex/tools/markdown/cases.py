from typing import ClassVar

from pipelex.tools.markdown.markdown_formatting import (
    FormattedBlock,
    FormattedCodeBlock,
    FormattedHeading,
    FormattedListItem,
    FormattedParagraph,
    FormattedRule,
    FormattedTable,
    FormattedTableCell,
    FormattedTableRow,
    TextSpan,
)

_ITEM = FormattedListItem(list_depth=1, marker="•", spans=[TextSpan(text="item")])
_ONE_CELL_ROWS = [
    FormattedTableRow(is_header=True, cells=[FormattedTableCell(spans=[TextSpan(text="a")])]),
    FormattedTableRow(is_header=False, cells=[FormattedTableCell(spans=[TextSpan(text="1")])]),
]


class MarkdownFormattingTestData:
    """Markdown texts the formatting tests read, and what each formats into."""

    # A header of three thousand columns over three hundred one-character rows: nine hundred thousand cells, which the
    # table rule pads every row to, out of about ten kilobytes of text.
    PADDED_TABLE: ClassVar[str] = "|" + "a|" * 3000 + "\n|" + "-|" * 3000 + "\n" + "|a\n" * 300

    # A header of twenty columns over ten one-character rows: its padded cells cost the parser more than the result
    # they format into takes, so charging either alone spends less than charging both.
    WIDE_SHORT_TABLE: ClassVar[str] = "Totals:\n\n|" + "h|" * 20 + "\n|" + "-|" * 20 + "\n" + "|a\n" * 10

    # A reference link used four thousand times, whose twenty-thousand-character address an engine printing a link's
    # address beside its text prints at every use: its text alone fits a budget, what it formats into does not.
    REUSED_REFERENCE: ClassVar[str] = "[a][r] " * 4000 + "\n\n[r]: https://example.com/" + "y" * 20000

    # A twenty-thousand-character address around ten thousand spans, alternating italic and plain: each span carries the
    # address, so the structure written out, as JSON or as its repr, writes it ten thousand times, two hundred megabytes
    # out of forty kilobytes of text.
    LINK_AROUND_MANY_SPANS: ClassVar[str] = "[" + "*a*b" * 5000 + "](https://example.com/" + "y" * 20000 + ")"

    # The same address around three spans, an ordinary text whose result carries the address three times.
    LINK_AROUND_FEW_SPANS: ClassVar[str] = "[*a* b *c*](https://example.com/" + "y" * 20000 + ")"

    # A report section repeated into about thirty thousand characters: an ordinary long text, well within one budget.
    LONG_REPORT: ClassVar[str] = "## Findings\n\nSome *text* with a [link](https://a.co), `code` and more.\n\n- one\n- two\n\n" * 300

    # Emphasis nested four hundred deep, and emphasis and strong emphasis alternating four hundred deep: markdown-it
    # pairs emphasis up without capping its depth, and a syntax tree that deep overflows Python's stack.
    DEEP_EMPHASIS: ClassVar[str] = "*a " * 400 + "b" + " c*" * 400
    DEEP_EMPHASIS_TEXT: ClassVar[str] = "a " * 400 + "b" + " c" * 400
    DEEP_MIXED_EMPHASIS: ClassVar[str] = "*a **b " * 200 + "middle" + " b** a*" * 200
    DEEP_MIXED_EMPHASIS_TEXT: ClassVar[str] = "a b " * 200 + "middle" + " b a" * 200

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

    # Blocks inside a list item, and its plain text: every line of what the item holds indented under its marker, a
    # code block's lines and a table's rows included, and a hard break's next line too.
    INSIDE_A_LIST_ITEM: ClassVar[str] = (
        "- item\n\n  ```\n  first\n\n  third\n  ```\n\n  | a | b |\n  | - | - |\n  | 1 | 2 |\n\n  > quoted  \n  > on\n\n  ---\n- \n- next\n"
    )
    INSIDE_A_LIST_ITEM_PLAIN_TEXT: ClassVar[str] = "• item\n  first\n\n  third\n  a\tb\n  1\t2\n  quoted\n  on\n•\n• next"

    # Each block nested in a list item or a quotation, by topic: (topic, the Markdown, the blocks it formats into).
    NESTING_CASES: ClassVar[list[tuple[str, str, list[FormattedBlock]]]] = [
        ("a list in a quotation", "> - item", [FormattedListItem(list_depth=1, quote_depth=1, marker="•", spans=[TextSpan(text="item")])]),
        ("a code block in a list item", "- item\n\n  ```\n  code\n  ```", [_ITEM, FormattedCodeBlock(list_depth=1, lines=["code"])]),
        ("a table in a list item", "- item\n\n  | a |\n  | - |\n  | 1 |", [_ITEM, FormattedTable(list_depth=1, rows=_ONE_CELL_ROWS)]),
        ("a rule in a list item", "- item\n\n  ---", [_ITEM, FormattedRule(list_depth=1)]),
        (
            "a quotation in a list item",
            "- item\n\n  > quoted",
            [_ITEM, FormattedParagraph(list_depth=1, quote_depth=1, spans=[TextSpan(text="quoted")])],
        ),
        ("a code block in a quotation", "> ```\n> code\n> ```", [FormattedCodeBlock(quote_depth=1, lines=["code"])]),
        ("a table in a quotation", "> | a |\n> | - |\n> | 1 |", [FormattedTable(quote_depth=1, rows=_ONE_CELL_ROWS)]),
        (
            "a rule in a quotation",
            "> before\n>\n> ---",
            [FormattedParagraph(quote_depth=1, spans=[TextSpan(text="before")]), FormattedRule(quote_depth=1)],
        ),
        (
            "a list in a quotation in a quotation",
            "> > - deep\n>\n> > back",
            [
                FormattedListItem(list_depth=1, quote_depth=2, marker="•", spans=[TextSpan(text="deep")]),
                FormattedParagraph(quote_depth=2, spans=[TextSpan(text="back")]),
            ],
        ),
        ("a heading in a quotation", "> # Title", [FormattedHeading(quote_depth=1, level=1, spans=[TextSpan(text="Title")])]),
    ]
