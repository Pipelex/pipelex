from json2html import json2html
from rich.pretty import Pretty
from rich.table import Table
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.markdown_utils import convert_to_markdown
from pipelex.tools.misc.pretty import MAX_RENDER_DEPTH, PrettyPrintable, PrettyPrinter
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
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
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
