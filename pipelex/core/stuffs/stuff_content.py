from abc import ABC
from typing import Any, TypeVar

from kajson import kajson
from rich.json import JSON
from typing_extensions import override

from pipelex.cogt.templating.templating_style import TextFormat
from pipelex.tools.misc.json_utils import remove_none_values
from pipelex.tools.misc.pretty import PrettyPrintable, PrettyPrinter, PrettyRenderable, pretty_print
from pipelex.tools.typing.pydantic_utils import CustomBaseModel

StuffContentType = TypeVar("StuffContentType", bound="StuffContent")


class StuffContent(PrettyRenderable, CustomBaseModel, ABC):
    @property
    def short_desc(self) -> str:
        return f"some {self.__class__.__name__}"

    def smart_dump(self) -> str | dict[str, Any] | list[str] | list[dict[str, Any]]:
        return self.model_dump(serialize_as_any=True)

    @override
    def __str__(self) -> str:
        return self.rendered_json()

    def rendered_str(self, text_format: TextFormat = TextFormat.PLAIN) -> str:
        match text_format:
            case TextFormat.PLAIN:
                return self.rendered_plain()
            case TextFormat.HTML:
                return self.rendered_html()
            case TextFormat.MARKDOWN:
                return self.rendered_markdown()
            case TextFormat.JSON:
                return self.rendered_json()
            case TextFormat.SPREADSHEET:
                return self.render_spreadsheet()

    def rendered_plain(self) -> str:
        return self.rendered_markdown()

    def rendered_html(self) -> str:
        """Default HTML rendering - subclasses can override for custom rendering."""
        return f"<pre>{self.rendered_json()}</pre>"

    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:  # noqa: ARG002
        """Default Markdown rendering - subclasses can override for custom rendering."""
        return f"```json\n{self.rendered_json()}\n```"

    def render_spreadsheet(self) -> str:
        return self.rendered_plain()

    def rendered_json(self) -> str:
        return kajson.dumps(self.smart_dump(), indent=4)

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        """Render content for pretty printing.

        Args:
            title: Optional title for the rendering
            depth: Current nesting depth, used to prevent nesting too many sub-tables which would end up too narrow in the console
        """
        json_content = remove_none_values(json_content=self.smart_dump())
        return JSON.from_data(json_content, indent=4)

    def pretty_print_content(self, title: str | None = None) -> None:
        pretty = self.rendered_pretty()
        width = PrettyPrinter.pretty_width()
        pretty_print(pretty, title=title, width=width)
