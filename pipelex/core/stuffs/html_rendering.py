import html as html_module
from datetime import date, datetime
from enum import Enum
from typing import Any, cast

from pipelex.core.stuffs.stuff_content import StuffContent


def render_value_html(value: Any) -> str:
    """Render a value as HTML, recursively handling nested structures.

    Shared by every content class that renders named sub-values as HTML
    (StructuredContent fields, CompositeContent components), so escaping and
    formatting behavior cannot drift between them.

    Uses match/case to handle all common Pydantic field types:
    - None: renders as <em>None</em>
    - StuffContent subclasses: calls rendered_html() recursively
    - str: escapes HTML (or passes through if already HTML)
    - bool: renders as "True" or "False" (must be before int, as bool is subclass of int)
    - int: renders as string
    - float: renders as string
    - Enum: renders the enum value
    - datetime/date: renders in ISO format
    - list/tuple: renders as <ul> list
    - dict: renders as <dl> definition list
    - Other: escapes string representation
    """
    match value:
        case None:
            return "<em>None</em>"

        case StuffContent():
            return value.rendered_html()

        case str():
            # If it looks like HTML (starts with <), render as-is
            stripped = value.strip()
            if stripped.startswith("<") and (">" in stripped):
                return value
            return html_module.escape(value)

        case bool():
            # Must be before int because bool is a subclass of int
            return "True" if value else "False"

        case int():
            return str(value)

        case float():
            return str(value)

        case Enum():
            # Handles StrEnum and regular Enum
            return html_module.escape(str(value.value))

        case datetime():
            return html_module.escape(value.isoformat())

        case date():
            return html_module.escape(value.isoformat())

        case list() | tuple():
            list_value = cast("list[Any]", value)
            if len(list_value) == 0:
                return "<em>empty</em>"
            items = [f"<li>{render_value_html(item)}</li>" for item in list_value]
            return f"<ul>{''.join(items)}</ul>"

        case dict():
            dict_value = cast("dict[str, Any]", value)
            if len(dict_value) == 0:
                return "<em>empty</em>"
            items = [f"<dt>{html_module.escape(str(key))}</dt><dd>{render_value_html(val)}</dd>" for key, val in dict_value.items()]
            return f"<dl>{''.join(items)}</dl>"

        case _:
            # Fallback for any other types
            return html_module.escape(str(value))
