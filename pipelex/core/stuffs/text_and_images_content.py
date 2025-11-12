from rich.console import Group
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.misc.file_utils import ensure_directory_exists
from pipelex.tools.misc.pretty import PrettyPrintable


class TextAndImagesContent(StuffContent):
    text: TextContent | None
    images: list[ImageContent] | None

    @property
    @override
    def short_desc(self) -> str:
        text_count = 1 if self.text else 0
        image_count = len(self.images) if self.images else 0
        return f"text and image content ({text_count} text, {image_count} images)"

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        if self.text:
            rendered = self.text.rendered_markdown(level=level, is_pretty=is_pretty)
        else:
            rendered = ""
        return rendered

    @override
    def rendered_html(self) -> str:
        if self.text:
            rendered = self.text.rendered_html()
        else:
            rendered = ""
        return rendered

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # If neither text nor images are present
        if not self.text and not self.images:
            return Text("(empty)", style="dim italic")

        # If only text is present, render as Markdown
        if self.text and not self.images:
            return Markdown(self.text.text)

        group = Group()

        # Add text section if present
        if self.text:
            group.renderables.append(Text("Text:", style="bold cyan"))
            group.renderables.append(Markdown(self.text.text))
            if self.images:
                group.renderables.append(Text())  # Add spacing

        # Add images section if present
        if self.images:
            # Check if any image has a caption (for table column headers)
            has_captions = any(image.caption for image in self.images)

            table = Table(
                title=f"Images ({len(self.images)}):",
                title_style="bold cyan",
                title_justify="left",
                show_header=True,
                header_style="dim",
                border_style="dim",
            )
            table.add_column("Index")
            table.add_column("URL", width=36)
            if has_captions:
                table.add_column("Caption", style="yellow italic")

            for idx, image in enumerate(self.images):
                index_text = Text.from_markup(f"[dim]img-[/dim][yellow]{idx}[/yellow]")
                display_url = f"{image.url[:35]}…" if len(image.url) > 36 else image.url
                url_markdown = Markdown(f"[{display_url}]({image.url})")
                if has_captions:
                    table.add_row(index_text, url_markdown, image.caption or "/")
                else:
                    table.add_row(index_text, url_markdown)

            group.renderables.append(table)

        return group

    def save_to_directory(self, directory: str):
        ensure_directory_exists(directory)
        if text_content := self.text:
            text_content.save_to_directory(directory=directory)
        if images := self.images:
            for image_content in images:
                image_content.save_to_directory(directory=directory)
