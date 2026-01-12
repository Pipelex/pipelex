import json

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from typing_extensions import override

from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.text_format import TextFormat
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_sync
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.tools.uri.uri_resolver import resolve_uri


class ImageContent(StuffContent):
    url: str
    display_link: str | None = None
    source_prompt: str | None = None
    source_negative_prompt: str | None = None
    caption: str | None = None
    mime_type: str | None = None
    size: ImageSize | None = None

    @property
    @override
    def content_type(self) -> str | None:
        return self.mime_type

    @property
    @override
    def short_desc(self) -> str:
        url_desc = resolve_uri(self.url).kind.desc
        return f"{url_desc} of an image"

    @override
    def rendered_plain(self) -> str:
        return self.url[:500]

    @override
    def rendered_html(self) -> str:
        template_source = '<img src="{{ url|e }}" class="msg-img">'
        return render_jinja2_sync(
            template_source=template_source,
            template_category=TemplateCategory.HTML,
            templating_context={
                "url": self.display_link or self.url,
            },
        )

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return f"![{self.url[:100]}]({self.url})"

    @override
    def rendered_json(self) -> str:
        return json.dumps({"image_url": self.url, "source_prompt": self.source_prompt})

    def render_with_images(
        self,
        registry: ImageRegistry,
        text_format: TextFormat,  # noqa: ARG002
    ) -> str:
        """Register this image and return a token."""
        image_index = registry.register_image(self)
        return f"[Image {image_index + 1}]"

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        group = Group()

        # title indicating it's an image:
        title_text = Text("Image:", style="bold cyan")
        group.renderables.append(title_text)

        # URL with clickable markdown link
        display_url = f"{self.url[:200]}…" if len(self.url) > 201 else self.url
        url_markdown = Markdown(f"**URL:** [{display_url}]({self.url})")
        group.renderables.append(url_markdown)

        # Display link if present
        if self.display_link is not None:
            link_text = Text()
            link_text.append("Display: ", style="bold")
            link_text.append("Open Image", style=f"cyan link {self.display_link}")
            group.renderables.append(link_text)

        # Caption if present
        if self.caption:
            caption_text = Text()
            caption_text.append("Caption: ", style="bold")
            caption_text.append(self.caption, style="yellow italic")
            group.renderables.append(caption_text)

        # Size if present
        if self.size:
            size_text = Text()
            size_text.append("Size: ", style="bold")
            size_text.append(f"{self.size.width}x{self.size.height}", style="dim")
            group.renderables.append(size_text)

        # Source prompt if present
        if self.source_prompt:
            group.renderables.append(Text())  # Add spacing
            prompt_text = Text()
            prompt_text.append("Source Prompt: ", style="bold")
            prompt_text.append(self.source_prompt, style="dim italic")
            group.renderables.append(prompt_text)

        # Source negative prompt if present
        if self.source_negative_prompt:
            group.renderables.append(Text())  # Add spacing
            negative_prompt_text = Text()
            negative_prompt_text.append("Source Negative Prompt: ", style="bold")
            negative_prompt_text.append(self.source_negative_prompt, style="dim italic")
            group.renderables.append(negative_prompt_text)

        # MIME type if present
        if self.mime_type:
            mime_type_text = Text()
            mime_type_text.append("MIME Type: ", style="bold")
            mime_type_text.append(self.mime_type, style="dim")
            group.renderables.append(mime_type_text)

        return group
