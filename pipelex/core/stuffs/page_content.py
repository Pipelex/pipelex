from rich.console import Group
from rich.markdown import Markdown
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
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # If there's no page_view, just return the text_and_images rendering
        if self.page_view is None:
            return self.text_and_images.rendered_pretty(depth=depth)

        # If there's a page_view, create a group with both
        group = Group()

        # Add the text and images content
        group.renderables.append(self.text_and_images.rendered_pretty(depth=depth))

        # Add the page view section
        group.renderables.append(Text("\nPage View:", style="bold cyan"))
        url_markdown = Markdown(f"[{self.page_view.url}…]({self.page_view.url})")
        group.renderables.append(url_markdown)

        return group

    def save_to_directory(self, directory: str):
        ensure_directory_exists(directory)
        self.text_and_images.save_to_directory(directory=directory)
        if page_view := self.page_view:
            page_view.save_to_directory(directory=directory, base_name="page_view")
