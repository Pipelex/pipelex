import html as html_module
from datetime import date, datetime
from enum import Enum
from typing import Any, cast

from rich.pretty import Pretty
from rich.table import Table
from typing_extensions import override

from pipelex.cogt.templating.text_format import TextFormat
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.image_renderable import ImageRenderable
from pipelex.tools.misc.markdown_utils import convert_to_markdown
from pipelex.tools.misc.pretty import MAX_RENDER_DEPTH, PrettyPrintable, PrettyPrinter
from pipelex.tools.typing.pydantic_utils import clean_model_to_dict


class StructuredContent(StuffContent):
    @property
    @override
    def short_desc(self) -> str:
        return f"some structured content of class {self.__class__.__name__}"

    @override
    def rendered_html(self) -> str:
        """Render the structured content as HTML, recursively handling nested StuffContent."""
        rows: list[str] = []
        for field_name in type(self).model_fields:
            field_value = getattr(self, field_name)
            if field_value is None:
                continue
            rendered_value = self._render_value_html(field_value)
            rows.append(f"<tr><th>{html_module.escape(field_name)}</th><td>{rendered_value}</td></tr>")
        if not rows:
            return "<table><tr><td><em>empty</em></td></tr></table>"
        return f"<table>{''.join(rows)}</table>"

    @override
    async def rendered_html_async(self) -> str:
        """Async version of rendered_html."""
        return self.rendered_html()

    def _render_value_html(self, value: Any) -> str:
        """Render a value as HTML, recursively handling nested structures.

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
                items = [f"<li>{self._render_value_html(item)}</li>" for item in list_value]
                return f"<ul>{''.join(items)}</ul>"

            case dict():
                dict_value = cast("dict[str, Any]", value)
                if len(dict_value) == 0:
                    return "<em>empty</em>"
                items = [f"<dt>{html_module.escape(str(key))}</dt><dd>{self._render_value_html(val)}</dd>" for key, val in dict_value.items()]
                return f"<dl>{''.join(items)}</dl>"

            case _:
                # Fallback for any other types
                return html_module.escape(str(value))

    @override
    def rendered_markdown(self, *, level: int = 1, is_pretty: bool = False) -> str:
        dict_dump = clean_model_to_dict(obj=self)
        return convert_to_markdown(data=dict_dump, level=level, is_pretty=is_pretty)

    # -------------------------------------------------------------------------
    # ImageRenderable protocol implementation
    # -------------------------------------------------------------------------

    def render_with_images(
        self,
        *,
        registry: ImageRegistry,
        text_format: TextFormat,
    ) -> str:
        """Render with image extraction - recursively handles nested structures.

        This implementation iterates through all model fields and recursively
        renders any nested ImageRenderable objects, including those in plain
        Python lists, tuples, and dicts.

        Args:
            registry: ImageRegistry to track discovered images
            text_format: Format for rendering text content

        Returns:
            String with [Image N] tokens where images appear
        """
        parts: list[str] = []
        for field_name in type(self).model_fields:
            field_value = getattr(self, field_name)
            if field_value is None:
                continue
            rendered = self._render_value_with_images(field_value, registry=registry, text_format=text_format)
            if rendered:
                parts.append(f"{field_name}: {rendered}")
        return "\n".join(parts)

    def _render_value_with_images(
        self,
        value: Any,
        *,
        registry: ImageRegistry,
        text_format: TextFormat,
    ) -> str:
        """Recursively render a value with image extraction.

        Args:
            value: The value to render (may be ImageRenderable, list, tuple, dict, or primitive)
            registry: ImageRegistry to track discovered images
            text_format: Format for rendering text content

        Returns:
            String representation with [Image N] tokens where images appear
        """
        if value is None:
            return ""
        if isinstance(value, ImageRenderable):
            return value.render_with_images(registry=registry, text_format=text_format)
        if isinstance(value, (list, tuple)):
            parts: list[str] = []
            list_value = cast("list[Any]", value)
            for item in list_value:
                rendered = self._render_value_with_images(item, registry=registry, text_format=text_format)
                if rendered:
                    parts.append(rendered)
            return "\n".join(parts)
        if isinstance(value, dict):
            dict_parts: list[str] = []
            dict_value = cast("dict[str, Any]", value)
            for key, val in dict_value.items():
                rendered = self._render_value_with_images(val, registry=registry, text_format=text_format)
                if rendered:
                    dict_parts.append(f"{key}: {rendered}")
            return "\n".join(dict_parts)
        if isinstance(value, StuffContent):
            return value.rendered_for_prompt(text_format=text_format)
        return str(value)

    # -------------------------------------------------------------------------
    # Pretty printing
    # -------------------------------------------------------------------------

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Check if we've exceeded maximum depth - fall back to Pretty rendering
        # Pretty shows the Python object structure beautifully, just like when calling pretty_print(stuff)
        if depth >= MAX_RENDER_DEPTH:
            return Pretty(self)

        table = Table(
            title=title,
            show_header=True,
            show_edge=False,
            show_lines=True,
            border_style="white",
            width=PrettyPrinter.pretty_width(depth=depth),
        )
        table.add_column("Attribute", style="cyan", justify="left")
        table.add_column("Value", style="white")

        # Get all fields from the model
        for field_name, field_value in self:
            # Skip None values and empty lists
            if field_value is None:
                continue
            if isinstance(field_value, list) and len(field_value) == 0:  # type: ignore[arg-type]
                continue

            pretty = PrettyPrinter.make_pretty(value=field_value, depth=depth + 1)
            table.add_row(field_name, pretty)

        return table
