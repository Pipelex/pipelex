from typing import Any

from json2html import json2html
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.markdown_utils import convert_to_markdown
from pipelex.tools.misc.pretty import PrettyPrintable, pretty_width
from pipelex.tools.typing.pydantic_utils import clean_model_to_dict


class StructuredContent(StuffContent):
    @property
    @override
    def short_desc(self) -> str:
        return f"some structured content of class {self.__class__.__name__}"

    @override
    def smart_dump(self):
        return self.model_dump(serialize_as_any=True)

    @override
    def rendered_html(self) -> str:
        dict_dump = clean_model_to_dict(obj=self)

        html: str = json2html.convert(  # pyright: ignore[reportAssignmentType, reportUnknownVariableType]
            json=dict_dump,  # pyright: ignore[reportArgumentType]
            clubbing=True,
            table_attributes="",
        )
        return html

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        dict_dump = clean_model_to_dict(obj=self)
        return convert_to_markdown(data=dict_dump, level=level, is_pretty=is_pretty)

    @override
    def rendered_for_rich(self, title: str | None = None, number: int | None = None) -> PrettyPrintable:
        table = Table(
            title=title,
            show_header=True,
            show_edge=False,
            show_lines=True,
            border_style="white",
            width=pretty_width(factor=0.8),
        )
        table.add_column("Attribute", style="cyan", justify="left")
        table.add_column("Value", style="white")

        def _make_pretty(value: Any) -> PrettyPrintable:
            pretty: PrettyPrintable
            # Format the value
            if isinstance(value, StuffContent):
                # If it's a StuffContent, use its rendered_for_rich method
                pretty = value.rendered_for_rich()
            elif isinstance(value, list):
                # For lists, build a table without headers
                list_table = Table(
                    show_header=False,
                    show_edge=False,
                    show_lines=True,
                    border_style="dim",
                    padding=(0, 1),
                )
                list_table.add_column("No.", style="yellow", justify="center", width=4)
                list_table.add_column("Item", style="white")

                for idx, item in enumerate(value, start=1):  # type: ignore[arg-type]
                    pretty_item = _make_pretty(item)
                    list_table.add_row(str(idx), pretty_item)

                pretty = list_table
            elif isinstance(value, str):
                pretty = Markdown(value)
            elif isinstance(value, (int, float, bool)):
                # For primitive types, convert to string
                pretty = Text(str(value))
            else:
                # For other types, use string representation
                pretty = Text(f"{value}")

            return pretty

        # Get all fields from the model
        for field_name, field_value in self:
            # Skip None values and empty lists
            if field_value is None:
                continue
            if isinstance(field_value, list) and len(field_value) == 0:  # type: ignore[arg-type]
                continue

            pretty = _make_pretty(value=field_value)
            table.add_row(field_name, pretty)

        return table
