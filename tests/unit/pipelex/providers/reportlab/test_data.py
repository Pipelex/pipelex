import datetime
from typing import ClassVar

from pipelex.cogt.doc_gen.layout_tree import (
    FieldGridBlock,
    ImageBlock,
    LayoutBlock,
    LayoutColumn,
    LayoutField,
    LayoutScalar,
    ParagraphsBlock,
    SectionBlock,
    TableBlock,
)
from tests.unit.pipelex.providers.reportlab.reportlab_test_helpers import png_data_url

MARKUP_VALUE = "<b>Tom & Jerry</b>"


def line_items_table(*, row_count: int) -> TableBlock:
    return TableBlock(
        title="Line items",
        path="invoice.line_items",
        columns=[
            LayoutColumn(key="description", label="Description"),
            LayoutColumn(key="quantity", label="Quantity"),
            LayoutColumn(key="amount", label="Amount"),
        ],
        rows=[
            {"description": f"Consulting day {index} of the project", "quantity": index % 5 + 1, "amount": 800.5 + index}
            for index in range(1, row_count + 1)
        ],
    )


class ReportlabRendererTestData:
    """Each markup case: (topic, blocks holding MARKUP_VALUE somewhere). Each script case: (language, sample)."""

    MARKUP_CASES: ClassVar[list[tuple[str, list[LayoutBlock]]]] = [
        ("field grid value", [FieldGridBlock(fields=[LayoutField(label="Customer", value=MARKUP_VALUE)])]),
        ("field grid label", [FieldGridBlock(fields=[LayoutField(label=MARKUP_VALUE, value="x")])]),
        ("paragraph", [ParagraphsBlock(paragraphs=[f"Dear {MARKUP_VALUE}, welcome."])]),
        ("section title", [SectionBlock(title=MARKUP_VALUE, level=1, blocks=[])]),
        ("short table cell", [TableBlock(title="T", path="t", columns=[LayoutColumn(key="name", label="Name")], rows=[{"name": MARKUP_VALUE}])]),
        (
            "wrapping table cell",
            [
                TableBlock(
                    title="T",
                    path="t",
                    columns=[LayoutColumn(key="name", label="Name"), LayoutColumn(key="notes", label="Notes")],
                    rows=[{"name": MARKUP_VALUE, "notes": "word " * 200}],
                )
            ],
        ),
        ("image caption", [ImageBlock(url=png_data_url(width=20, height=10), caption=MARKUP_VALUE)]),
    ]

    SCRIPT_CASES: ClassVar[list[tuple[str, str]]] = [
        ("Polish", "Zażółć gęślą jaźń"),
        ("Czech", "Příliš žluťoučký kůň"),
        ("Greek", "Καλημέρα κόσμε"),
        ("Cyrillic", "Съешь же ещё этих мягких французских булок"),
        ("Vietnamese", "Tiếng Việt có dấu"),
    ]

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
        ("As written", "As written"),
    ]


class MarkdownFlowablesTestData:
    """Each link case: (href, whether it becomes a link)."""

    NESTED_LISTS = "1. alpha\n2. beta\n   1. gamma\n   2. delta\n      - epsilon\n3. zeta\n4. eta\n"

    # CommonMark lets only a list starting at 1 interrupt a paragraph, so a nested list with its own start follows a blank line.
    STARTED_LISTS = "7. seven\n8. eight\n\n   3. three\n   4. four\n\n9. nine\n"

    LINK_CASES: ClassVar[list[tuple[str, bool]]] = [
        ("https://pipelex.com", True),
        ("HTTP://PIPELEX.COM", True),
        ("mailto:team@pipelex.com", True),
        ("javascript:alert(1)", False),
        (" JaVaScRiPt:alert(1)", False),
        ("ftp://example.com/file", False),
        ("file:///etc/passwd", False),
        ("data:text/html,<b>x</b>", False),
        ("relative/page.md", False),
        ("#anchor", False),
        ("http://[invalid", False),
    ]
