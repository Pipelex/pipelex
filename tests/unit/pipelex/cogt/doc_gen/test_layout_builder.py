import datetime

from pydantic import Field

from pipelex.cogt.doc_gen.layout_builder import build_layout_document
from pipelex.cogt.doc_gen.layout_tree import FieldGridBlock, ImageBlock, MarkdownBlock, ParagraphsBlock, SectionBlock, TableBlock
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent


class _LineItem(StructuredContent):
    description: str
    quantity: int
    unit_price: float = Field(title="Unit price (EUR)")


class _Customer(StructuredContent):
    name: str
    city: str


class _Invoice(StructuredContent):
    number: str
    issued_on: datetime.date
    tags: list[str]
    customer: _Customer
    line_items: list[_LineItem]


def _invoice() -> _Invoice:
    return _Invoice(
        number="INV-1",
        issued_on=datetime.date(2026, 9, 30),
        tags=["urgent", "paid"],
        customer=_Customer(name="Ada", city="Paris"),
        line_items=[_LineItem(description="Tea", quantity=2, unit_price=3.5), _LineItem(description="Cake", quantity=1, unit_price=4.0)],
    )


class TestLayoutBuilder:
    def test_a_single_structure_fills_the_top_level(self) -> None:
        document = build_layout_document(title="Invoice", named_contents=[("invoice", _invoice())])

        grid, customer, table = document.blocks
        assert isinstance(grid, FieldGridBlock)
        assert [(field.label, field.value) for field in grid.fields] == [
            ("Number", "INV-1"),
            ("Issued on", datetime.date(2026, 9, 30)),
            ("Tags", "urgent, paid"),
        ]
        assert isinstance(customer, SectionBlock)
        assert customer.title == "Customer"
        assert isinstance(table, TableBlock)
        assert table.path == "invoice.line_items"
        assert [column.label for column in table.columns] == ["Description", "Quantity", "Unit price (EUR)"]
        assert table.rows[1] == {"description": "Cake", "quantity": 1, "unit_price": 4.0}

    def test_a_single_markdown_input_is_the_whole_body(self) -> None:
        document = build_layout_document(title="Report", named_contents=[("report", MarkdownContent(text="# Findings\n\n**Bold** claim."))])
        assert document.blocks == [MarkdownBlock(markdown="# Findings\n\n**Bold** claim.")]

    def test_a_single_text_input_prints_as_paragraphs(self) -> None:
        document = build_layout_document(title="Notice", named_contents=[("notice", TextContent(text="First.\n\nSecond, with **stars**."))])
        assert document.blocks == [ParagraphsBlock(paragraphs=["First.", "Second, with **stars**."])]

    def test_several_inputs_get_a_section_each_in_order(self) -> None:
        document = build_layout_document(
            title="Pack",
            named_contents=[
                ("summary", TextContent(text="All good.")),
                ("cover_image", ImageContent(url="pipelex-storage://s/cover.png")),
                ("invoice", _invoice()),
            ],
        )

        summary, image, invoice = document.blocks
        assert isinstance(summary, SectionBlock)
        assert summary.title == "Summary"
        assert image == ImageBlock(url="pipelex-storage://s/cover.png", caption="Cover image")
        assert isinstance(invoice, SectionBlock)
        assert invoice.title == "Invoice"
        assert document.image_urls() == ["pipelex-storage://s/cover.png"]

    def test_a_list_input_of_flat_structures_is_a_table(self) -> None:
        items = ListContent[_LineItem](items=[_LineItem(description="Tea", quantity=2, unit_price=3.5)])
        document = build_layout_document(title="Items", named_contents=[("line_items", items)])

        (table,) = document.blocks
        assert isinstance(table, TableBlock)
        assert table.title == "Line items"

    def test_a_list_input_of_images_prints_each_image(self) -> None:
        photos = ListContent[ImageContent](
            items=[ImageContent(url="pipelex-storage://s/front.png"), ImageContent(url="pipelex-storage://s/back.png", caption="Back")]
        )
        document = build_layout_document(title="Photos", named_contents=[("photos", photos)])

        (section,) = document.blocks
        assert isinstance(section, SectionBlock)
        assert section.blocks == [
            ImageBlock(url="pipelex-storage://s/front.png", caption="Photo 1"),
            ImageBlock(url="pipelex-storage://s/back.png", caption="Back"),
        ]
        assert document.image_urls() == ["pipelex-storage://s/front.png", "pipelex-storage://s/back.png"]

    def test_a_list_input_of_markdown_formats_each_text(self) -> None:
        sections = ListContent[MarkdownContent](items=[MarkdownContent(text="# One"), MarkdownContent(text="**Two**")])
        document = build_layout_document(title="Report", named_contents=[("sections", sections)])

        (section,) = document.blocks
        assert isinstance(section, SectionBlock)
        first, second = section.blocks
        assert isinstance(first, SectionBlock)
        assert first.blocks == [MarkdownBlock(markdown="# One")]
        assert isinstance(second, SectionBlock)
        assert second.blocks == [MarkdownBlock(markdown="**Two**")]

    def test_a_structure_field_listing_images_prints_them(self) -> None:
        class _Inspection(StructuredContent):
            site: str
            photos: list[ImageContent]

        inspection = _Inspection(site="Roof", photos=[ImageContent(url="pipelex-storage://s/a.png"), ImageContent(url="pipelex-storage://s/b.png")])
        document = build_layout_document(title="Inspection", named_contents=[("inspection", inspection)])

        assert not any(isinstance(block, TableBlock) for block in document.blocks)
        assert document.image_urls() == ["pipelex-storage://s/a.png", "pipelex-storage://s/b.png"]

    def test_an_html_input_prints_its_visible_text(self) -> None:
        document = build_layout_document(
            title="Page", named_contents=[("page", HtmlContent(inner_html="<h1>Title</h1><script>alert(1)</script><p>Body <b>text</b>.</p>"))]
        )

        assert document.blocks == [ParagraphsBlock(paragraphs=["Title", "Body text."])]
