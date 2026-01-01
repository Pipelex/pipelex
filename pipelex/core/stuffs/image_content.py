import json

from typing_extensions import override

from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_sync
from pipelex.tools.misc.path_utils import interpret_path_or_url


class ImageContent(StuffContent):
    url: str
    display_link: str | None = None
    source_prompt: str | None = None
    caption: str | None = None
    mime_type: str | None = None
    size: ImageSize | None = None

    @property
    @override
    def short_desc(self) -> str:
        url_desc = interpret_path_or_url(path_or_uri=self.url).desc
        return f"{url_desc} or an image"

    @override
    def rendered_plain(self) -> str:
        return self.url[:500]

    @override
    def rendered_html(self) -> str:
        template_source = '<img src="{{ url|e }}" class="msg-img">'
        return render_jinja2_sync(
            template_source=template_source,
            template_category=TemplateCategory.HTML,
            temlating_context={
                "url": self.url,
            },
        )

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return f"![{self.url[:100]}]({self.url})"

    @override
    def rendered_json(self) -> str:
        return json.dumps({"image_url": self.url, "source_prompt": self.source_prompt})
