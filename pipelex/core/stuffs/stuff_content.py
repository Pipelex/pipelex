from abc import ABC
from typing import Any, TypeVar

from kajson import kajson
from rich.json import JSON
from typing_extensions import override

from pipelex.cogt.templating.text_format import TextFormat
from pipelex.tools.jinja2.image_registry import ImageRegistry
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

    # -------------------------------------------------------------------------
    # Protected sync implementations - override these in subclasses for sync operations
    # -------------------------------------------------------------------------

    def _render_plain(self) -> str:
        """Sync plain text rendering - defaults to markdown."""
        return self._render_markdown()

    def _render_html(self) -> str:
        """Sync HTML rendering - defaults to JSON in pre tags."""
        return f"<pre>{self._render_json()}</pre>"

    def _render_markdown(self, level: int = 1, is_pretty: bool = False) -> str:  # noqa: ARG002
        """Sync Markdown rendering - defaults to JSON in code block."""
        return f"```json\n{self._render_json()}\n```"

    def _render_json(self) -> str:
        """Sync JSON rendering - defaults to kajson.dumps of smart_dump."""
        return kajson.dumps(self.smart_dump(), indent=4)

    def _render_spreadsheet(self) -> str:
        """Sync spreadsheet rendering - defaults to plain text."""
        return self._render_plain()

    # -------------------------------------------------------------------------------------
    # Public async interface - for Jinja2 filter compatibility
    # Override these in subclasses that need async operations (e.g., container recursion)
    # -------------------------------------------------------------------------------------

    async def rendered_str(self, text_format: TextFormat = TextFormat.PLAIN) -> str:
        match text_format:
            case TextFormat.PLAIN:
                return await self.rendered_plain()
            case TextFormat.HTML:
                return await self.rendered_html()
            case TextFormat.MARKDOWN:
                return await self.rendered_markdown()
            case TextFormat.JSON:
                return await self.rendered_json()
            case TextFormat.SPREADSHEET:
                return await self.render_spreadsheet()

    async def rendered_plain(self) -> str:
        return self._render_plain()

    async def rendered_html(self) -> str:
        """Default HTML rendering - subclasses can override for custom rendering."""
        return self._render_html()

    async def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        """Default Markdown rendering - subclasses can override for custom rendering."""
        return self._render_markdown(level=level, is_pretty=is_pretty)

    async def render_spreadsheet(self) -> str:
        return self._render_spreadsheet()

    async def rendered_json(self) -> str:
        return self._render_json()

    # -------------------------------------------------------------------------
    # ImageRenderable protocol implementation
    # -------------------------------------------------------------------------

    def render_with_images(
        self,
        registry: ImageRegistry,
        text_format: TextFormat,
    ) -> str:
        """Render with image extraction - default iterates model fields.

        This base implementation iterates through all model fields and recursively
        renders any nested ImageRenderable objects, registering images as it goes.

        Args:
            registry: ImageRegistry to track discovered images
            text_format: Format for rendering text content

        Returns:
            String with [Image N] tokens where images appear
        """
        from pipelex.tools.jinja2.image_renderable import ImageRenderable  # noqa: PLC0415

        parts: list[str] = []
        for field_name in type(self).model_fields:
            field_value = getattr(self, field_name)
            if field_value is None:
                continue
            if isinstance(field_value, ImageRenderable):
                rendered = field_value.render_with_images(registry, text_format)
            else:
                rendered = str(field_value)
            if rendered:
                parts.append(f"{field_name}: {rendered}")
        return "\n".join(parts)

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
    async def rendered_pretty_html(self, title: str | None = None, width: int | None = None) -> str:
        return await self.rendered_html()
