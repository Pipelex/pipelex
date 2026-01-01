from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from typing_extensions import override

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
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
        link = self.page_view.display_link
        if link is not None:
            link_text = Text("Display", style=f"cyan link {link}")
            group.renderables.append(link_text)

        return group
