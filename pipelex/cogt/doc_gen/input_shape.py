"""The shape of a step's inputs as plain data, which a template checker compares a template file with.

An office template is filled from plain data (`plain_data.py`), so what a checker needs to know is the shape
of that data: which fields each input has, which of them are lists, and what their items hold. It learns it
from an `InputShape` tree per input rather than from Pipelex's concepts and classes, which keeps the checker
on the plugin contract (`template_check.py`).
"""

import datetime
import types
import typing
from collections.abc import Iterable, Sequence
from decimal import Decimal
from enum import Enum, StrEnum
from typing import Any, Literal, Union

from pydantic import BaseModel, Field

from pipelex.cogt.doc_gen.plain_data import plain_data
from pipelex.core.stuffs.choice_content import ChoiceContent
from pipelex.core.stuffs.composite_content import CompositeContent
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.core.stuffs.yes_no_content import YesNoContent


class InputShapeKind(StrEnum):
    TEXT = "text"
    MARKDOWN = "markdown"
    HTML = "html"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    TIME = "time"
    IMAGE = "image"
    DOCUMENT = "document"
    STRUCTURE = "structure"
    LIST = "list"
    ANY = "any"


class InputShape(BaseModel):
    """One value's shape as plain data.

    A structure lists its `fields`, which an image and a document also do (their URL among them, which an
    engine reads through `RenderResources`); a list has its `item`; anything else is a leaf. `ANY` is a value
    whose shape is not declared, such as a JSON input, so a checker cannot tell what it holds. A native `Date`
    is `DATE`, and its plain data is a `datetime.date`, or a `datetime.datetime`, which is one too, when it
    carries a time of day.
    """

    kind: InputShapeKind = Field(strict=False)
    title: str | None = None
    description: str | None = None
    fields: dict[str, "InputShape"] = Field(default_factory=dict)
    item: "InputShape | None" = None


InputShape.model_rebuild()

_NONE_TYPE = type(None)


def _leaf(kind: InputShapeKind, *, title: str | None = None, description: str | None = None) -> InputShape:
    return InputShape(kind=kind, title=title, description=description)


def _content_leaf_kind(content_class: type[BaseModel]) -> InputShapeKind | None:
    """The leaf kind of a native content class, whose plain data is a single value; None for any other class."""
    if issubclass(content_class, MarkdownContent):
        return InputShapeKind.MARKDOWN
    if issubclass(content_class, TextContent):
        return InputShapeKind.TEXT
    if issubclass(content_class, HtmlContent):
        return InputShapeKind.HTML
    if issubclass(content_class, NumberContent):
        return InputShapeKind.NUMBER
    if issubclass(content_class, YesNoContent):
        return InputShapeKind.BOOLEAN
    if issubclass(content_class, ChoiceContent):
        return InputShapeKind.TEXT
    if issubclass(content_class, RatingContent):
        return InputShapeKind.NUMBER
    if issubclass(content_class, DateContent):
        return InputShapeKind.DATE
    if issubclass(content_class, TimeContent):
        return InputShapeKind.TIME
    if issubclass(content_class, (JSONContent, ListContent, CompositeContent)):
        return InputShapeKind.ANY
    return None


def shape_of_class(content_class: type[BaseModel], *, title: str | None = None, description: str | None = None) -> InputShape:
    """The plain-data shape of a content class, or of any pydantic class nested in one."""
    return _shape_of_class(content_class=content_class, title=title, description=description, seen=frozenset())


def _shape_of_class(*, content_class: type[BaseModel], title: str | None, description: str | None, seen: frozenset[type]) -> InputShape:
    leaf_kind = _content_leaf_kind(content_class)
    if leaf_kind is not None:
        return _leaf(leaf_kind, title=title, description=description)
    if content_class in seen:
        # A recursive structure: the level that repeats is not described again.
        return _leaf(InputShapeKind.ANY, title=title, description=description)
    kind = InputShapeKind.STRUCTURE
    if issubclass(content_class, ImageContent):
        kind = InputShapeKind.IMAGE
    elif issubclass(content_class, DocumentContent):
        kind = InputShapeKind.DOCUMENT
    fields: dict[str, InputShape] = {}
    for field_name, field_info in content_class.model_fields.items():
        fields[field_name] = _shape_of_annotation(
            annotation=field_info.annotation,
            title=field_info.title,
            description=field_info.description,
            seen=seen | {content_class},
        )
    return InputShape(kind=kind, title=title, description=description, fields=fields)


def _shape_of_annotation(*, annotation: Any, title: str | None, description: str | None, seen: frozenset[type]) -> InputShape:
    origin = typing.get_origin(annotation)
    if origin in {Union, types.UnionType}:
        members = [member for member in typing.get_args(annotation) if member is not _NONE_TYPE]
        if len(members) == 1:
            return _shape_of_annotation(annotation=members[0], title=title, description=description, seen=seen)
        return _leaf(InputShapeKind.ANY, title=title, description=description)
    if origin is typing.Annotated:
        return _shape_of_annotation(annotation=typing.get_args(annotation)[0], title=title, description=description, seen=seen)
    if origin is Literal:
        return _leaf(_kind_of_values(values=typing.get_args(annotation)), title=title, description=description)
    if origin in {list, tuple, set, frozenset, Sequence}:
        item_args = typing.get_args(annotation)
        item = _shape_of_annotation(annotation=item_args[0], title=None, description=None, seen=seen) if item_args else _leaf(InputShapeKind.ANY)
        return InputShape(kind=InputShapeKind.LIST, title=title, description=description, item=item)
    if origin is not None or not isinstance(annotation, type):
        return _leaf(InputShapeKind.ANY, title=title, description=description)
    if issubclass(annotation, BaseModel):
        return _shape_of_class(content_class=annotation, title=title, description=description, seen=seen)
    scalar_type: type = annotation  # pyright: ignore[reportUnknownVariableType]
    return _leaf(_scalar_kind(scalar_type), title=title, description=description)


def _kind_of_values(*, values: Iterable[Any]) -> InputShapeKind:
    """The kind every one of these values has as plain data, an enum member being its value; `ANY` when they differ.

    A `None` among them is left out, as an optional field's is.
    """
    kinds: set[InputShapeKind] = set()
    for value in values:
        if value is not None:
            plain_value: object = plain_data(value)
            kinds.add(_scalar_kind(type(plain_value)))
    if len(kinds) == 1:
        return kinds.pop()
    return InputShapeKind.ANY


def _scalar_kind(annotation: type) -> InputShapeKind:
    if issubclass(annotation, Enum):
        enum_class: type[Enum] = annotation
        return _kind_of_values(values=[member.value for member in enum_class])
    if issubclass(annotation, bool):
        return InputShapeKind.BOOLEAN
    if issubclass(annotation, (int, float, Decimal)):
        return InputShapeKind.NUMBER
    if issubclass(annotation, str):
        return InputShapeKind.TEXT
    if issubclass(annotation, datetime.datetime):
        return InputShapeKind.DATETIME
    if issubclass(annotation, datetime.date):
        return InputShapeKind.DATE
    if issubclass(annotation, datetime.time):
        return InputShapeKind.TIME
    return InputShapeKind.ANY


def shape_of_input(*, content_class: type[BaseModel] | None, is_list: bool) -> InputShape:
    """The plain-data shape of one declared input: its content class's, or a list of it for a list input.

    An input whose concept declares no content class, `Anything`, has a shape that is not declared.
    """
    shape = shape_of_class(content_class) if content_class is not None else _leaf(InputShapeKind.ANY)
    if is_list:
        return InputShape(kind=InputShapeKind.LIST, item=shape)
    return shape
