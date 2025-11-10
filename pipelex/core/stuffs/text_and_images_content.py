from rich.console import Group
from rich.markdown import Markdown
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
    def rendered_for_rich(self) -> PrettyPrintable:
        has_text = self.text is not None
        has_images = self.images is not None and len(self.images) > 0

        # If only text is present, render as Markdown
        if has_text and not has_images:
            assert self.text is not None
            return Markdown(self.text.text)

        # If neither text nor images are present
        if not has_text and not has_images:
            return Text("(empty)", style="dim italic")

        # If we have images or both text and images, create a group
        group = Group()

        # Add text section if present
        if has_text:
            assert self.text is not None
            group.renderables.append(Text("Text:", style="bold cyan"))
            group.renderables.append(Markdown(self.text.text))
            if has_images:
                group.renderables.append(Text())  # Add spacing

        # Add images section if present
        if has_images:
            assert self.images is not None
            image_count = len(self.images)
            group.renderables.append(Text(f"Images ({image_count}):", style="bold cyan"))
            for idx, image in enumerate(self.images, start=1):
                image_info = f"  {idx}. {image.url}"
                if image.caption:
                    image_info += f" - {image.caption}"
                group.renderables.append(Text(image_info, style="dim"))

        return group

    def save_to_directory(self, directory: str):
        ensure_directory_exists(directory)
        if text_content := self.text:
            text_content.save_to_directory(directory=directory)
        if images := self.images:
            for image_content in images:
                image_content.save_to_directory(directory=directory)
