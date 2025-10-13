from typing_extensions import override

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.misc.file_utils import ensure_directory_exists


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

    def save_to_directory(self, directory: str):
        ensure_directory_exists(directory)
        if text_content := self.text:
            text_content.save_to_directory(directory=directory)
        if images := self.images:
            for image_content in images:
                image_content.save_to_directory(directory=directory)
