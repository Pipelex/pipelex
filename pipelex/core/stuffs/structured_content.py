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

        # Get all fields from the model
        for field_name, field_value in self:
            # Skip None values and empty lists
            if field_value is None:
                continue
            if isinstance(field_value, list) and len(field_value) == 0:  # type: ignore[arg-type]
                continue

            # Format the value
            if isinstance(field_value, StuffContent):
                # If it's a StuffContent, use its rendered_for_rich method
                value_content = field_value.rendered_for_rich()
            # elif isinstance(field_value, list):
            #     # For lists, show a simple representation
            #     value_content = Text(f"[{len(field_value)} items]", style="dim")  # type: ignore[arg-type]
            elif isinstance(field_value, str):
                value_content = Markdown(field_value)
            elif isinstance(field_value, (int, float, bool)):
                # For primitive types, convert to string
                value_content = Text(str(field_value))
            else:
                # For other types, use string representation
                value_content = Text(f"{field_value}", style="dim")

            table.add_row(field_name, value_content)

        return table
