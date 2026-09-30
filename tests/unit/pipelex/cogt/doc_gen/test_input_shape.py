import datetime
from typing import Literal

from pydantic import Field

from pipelex.cogt.doc_gen.input_shape import InputShape, InputShapeKind, shape_of_class, shape_of_input
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent


class _LineItem(StructuredContent):
    description: str
    amount: float = Field(title="Amount", description="In euros")


class _Node(StructuredContent):
    name: str
    children: list["_Node"]


class _Invoice(StructuredContent):
    number: str
    status: Literal["draft", "paid"]
    issued_at: datetime.datetime
    due_on: datetime.date | None = None
    is_paid: bool
    line_items: list[_LineItem]
    logo: ImageContent | None = None


class TestInputShape:
    def test_a_structure_lists_its_fields_with_their_kinds(self) -> None:
        shape = shape_of_class(_Invoice)

        assert shape.kind == InputShapeKind.STRUCTURE
        kinds = {field_name: field_shape.kind for field_name, field_shape in shape.fields.items()}
        assert kinds == {
            "number": InputShapeKind.TEXT,
            "status": InputShapeKind.TEXT,
            "issued_at": InputShapeKind.DATETIME,
            "due_on": InputShapeKind.DATE,
            "is_paid": InputShapeKind.BOOLEAN,
            "line_items": InputShapeKind.LIST,
            "logo": InputShapeKind.IMAGE,
        }

    def test_a_list_field_describes_its_items(self) -> None:
        line_items = shape_of_class(_Invoice).fields["line_items"]

        assert line_items.item is not None
        amount = line_items.item.fields["amount"]
        assert amount.kind == InputShapeKind.NUMBER
        assert amount.title == "Amount"
        assert amount.description == "In euros"

    def test_native_contents_are_leaves(self) -> None:
        assert shape_of_class(TextContent).kind == InputShapeKind.TEXT
        assert shape_of_class(MarkdownContent).kind == InputShapeKind.MARKDOWN
        assert "url" in shape_of_class(ImageContent).fields

    def test_a_recursive_structure_stops_where_it_repeats(self) -> None:
        children = shape_of_class(_Node).fields["children"]
        assert children.item is not None
        assert children.item.kind == InputShapeKind.ANY

    def test_a_list_input_is_a_list_of_its_concept(self) -> None:
        shape = shape_of_input(content_class=_LineItem, is_list=True)
        assert shape.kind == InputShapeKind.LIST
        assert shape.item is not None
        assert shape.item.kind == InputShapeKind.STRUCTURE

    def test_an_input_without_a_content_class_has_an_undeclared_shape(self) -> None:
        assert shape_of_input(content_class=None, is_list=False).kind == InputShapeKind.ANY
        list_shape = shape_of_input(content_class=None, is_list=True)
        assert list_shape.kind == InputShapeKind.LIST
        assert list_shape.item is not None
        assert list_shape.item.kind == InputShapeKind.ANY

    def test_a_shape_round_trips_through_json(self) -> None:
        shape = shape_of_class(_Invoice)
        assert InputShape.model_validate_json(shape.model_dump_json()) == shape
