"""Stuff contents as plain Python data, the shape an office template sees.

An office template is filled by its engine from plain data: a Word template reads `{{ invoice.number }}`
and an Excel template finds `invoice_number` by name, and neither knows what a stuff is. So a list stuff
becomes a list, a text stuff its text, a number its number, and a structure a dict of its fields.
Dates stay dates, so a spreadsheet cell keeps its type. That holds for an engine printing in the same process;
once serialized to JSON, a date is its ISO text.
"""

import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.core.stuffs.yes_no_content import YesNoContent


def plain_data(value: Any) -> Any:
    """Turn a stuff content, or any value found inside one, into plain Python data."""
    match value:
        case ListContent():
            return [plain_data(item) for item in value.items]  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        case TextContent():
            return value.text
        case HtmlContent():
            return value.inner_html
        case NumberContent():
            return value.number
        case YesNoContent():
            return value.yes_no
        case DateContent():
            if value.time is None:
                return value.date
            return datetime.datetime.combine(value.date, value.time)
        case TimeContent():
            return value.time
        case JSONContent():
            return value.json_obj
        case BaseModel():
            return _structure_plain_data(structure=value)
        case list() | tuple():
            return [plain_data(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
        case set() | frozenset():
            # A set has no order of its own, so its items are sorted for a document that reads the same on every run.
            return sorted((plain_data(item) for item in value), key=str)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        case dict():
            return {str(key): plain_data(item) for key, item in value.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        case Enum():
            return plain_data(value.value)
        case Decimal():
            return float(value)
        case _:
            return value


def _structure_plain_data(*, structure: BaseModel) -> dict[str, Any]:
    """A structure's declared fields, then its public extra fields, which is where `CompositeContent` holds its parts.

    The extra fields are read from `model_extra` and never with getattr, so a part named like a pydantic attribute
    resolves to the part.
    """
    fields: dict[str, Any] = {}
    for field_name in type(structure).model_fields:
        fields[field_name] = plain_data(getattr(structure, field_name))
    for field_name, value in (structure.model_extra or {}).items():
        if not field_name.startswith("_"):
            fields[field_name] = plain_data(value)
    return fields
