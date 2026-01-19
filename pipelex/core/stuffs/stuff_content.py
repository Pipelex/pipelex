from abc import ABC
from typing import Any, TypeVar

from kajson import kajson
from rich.json import JSON
from typing_extensions import override

from pipelex.cogt.templating.text_format import TextFormat
from pipelex.tools.misc.pretty import PrettyPrintable, PrettyPrinter, PrettyRenderable, pretty_print
from pipelex.tools.typing.pydantic_utils import CustomBaseModel

StuffContentType = TypeVar("StuffContentType", bound="StuffContent")


class StuffContent(PrettyRenderable, CustomBaseModel, ABC):
    @property
    def content_type(self) -> str | None:
        """Return the MIME type of the content, or None if not applicable."""
        return None

    @property
    def short_desc(self) -> str:
        return f"some {self.__class__.__name__}"

    def smart_dump(self) -> str | dict[str, Any] | list[str] | list[dict[str, Any]]:
        return self.model_dump(serialize_as_any=True)

    # -------------------------------------------------------------------------------------
    # Sync implementations - override these in subclasses for sync operations
    # -------------------------------------------------------------------------------------

    def rendered_plain(self) -> str:
        """Sync plain text rendering - defaults to markdown."""
        return self.rendered_markdown()

    def rendered_html(self) -> str:
        """Sync HTML rendering - defaults to JSON in pre tags."""
        return f"<pre>{self.rendered_json()}</pre>"

    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:  # noqa: ARG002
        """Sync Markdown rendering - defaults to JSON in code block."""
        return f"```json\n{self.rendered_json()}\n```"

    def rendered_json(self) -> str:
        """Sync JSON rendering - defaults to kajson.dumps of smart_dump."""
        return kajson.dumps(self.smart_dump(), indent=4)

    def rendered_str(self, text_format: TextFormat = TextFormat.PLAIN) -> str:
        """Sync rendering based on text format."""
        match text_format:
            case TextFormat.PLAIN:
                return self.rendered_plain()
            case TextFormat.HTML:
                return self.rendered_html()
            case TextFormat.MARKDOWN:
                return self.rendered_markdown()
            case TextFormat.JSON:
                return self.rendered_json()

    # -------------------------------------------------------------------------------------
    # Override these in subclasses that need async operations
    # -------------------------------------------------------------------------------------

    async def rendered_str_async(self, text_format: TextFormat = TextFormat.PLAIN) -> str:
        match text_format:
            case TextFormat.PLAIN:
                return await self.rendered_plain_async()
            case TextFormat.HTML:
                return await self.rendered_html_async()
            case TextFormat.MARKDOWN:
                return await self.rendered_markdown_async()
            case TextFormat.JSON:
                return await self.rendered_json_async()

    async def rendered_plain_async(self) -> str:
        return self.rendered_plain()

    async def rendered_html_async(self) -> str:
        """Default HTML rendering - subclasses can override for custom rendering."""
        return self.rendered_html()

    async def rendered_markdown_async(self, level: int = 1, is_pretty: bool = False) -> str:
        """Default Markdown rendering - subclasses can override for custom rendering."""
        return self.rendered_markdown(level=level, is_pretty=is_pretty)

    async def rendered_json_async(self) -> str:
        return self.rendered_json()

    # -------------------------------------------------------------------------
    # Pretty printing
    # -------------------------------------------------------------------------

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        """Render content for pretty printing.

        Args:
            title: Optional title for the rendering
            depth: Current nesting depth, used to prevent nesting too many sub-tables which would end up too narrow in the console
        """
        json_data = self.smart_dump()
        return JSON.from_data(json_data, indent=4)

    def pretty_print_content(self, title: str | None = None) -> None:
        pretty = self.rendered_pretty()
        width = PrettyPrinter.pretty_width()
        pretty_print(pretty, title=title, width=width)

    @override
    def rendered_pretty_html(self, title: str | None = None, width: int | None = None) -> str:
        return self.rendered_html()
