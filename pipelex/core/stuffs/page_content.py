from rich.console import Group
from rich.text import Text
from typing_extensions import override

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.tools.misc.file_utils import ensure_directory_exists
from pipelex.tools.misc.pretty import PrettyPrintable


class PageContent(StructuredContent):
    text_and_images: TextAndImagesContent
    page_view: ImageContent | None = None

    @override
    def rendered_for_rich(self) -> PrettyPrintable:
        # If there's no page_view, just return the text_and_images rendering
        if self.page_view is None:
            return self.text_and_images.rendered_for_rich()

        # If there's a page_view, create a group with both
        group = Group()

        # Add the text and images content
        group.renderables.append(self.text_and_images.rendered_for_rich())

        # Add spacing
        group.renderables.append(Text())

        # Add the page view section
        group.renderables.append(Text("Page View:", style="bold cyan"))
        page_view_info = f"  {self.page_view.url}"
        group.renderables.append(Text(page_view_info, style="dim"))

        return group

    def save_to_directory(self, directory: str):
        ensure_directory_exists(directory)
        self.text_and_images.save_to_directory(directory=directory)
        if page_view := self.page_view:
            page_view.save_to_directory(directory=directory, base_name="page_view")
