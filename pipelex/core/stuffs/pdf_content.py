from typing_extensions import override

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async
from pipelex.tools.uri.uri_resolver import resolve_uri


class PDFContent(StuffContent):
    url: str

    @property
    @override
    def content_type(self) -> str | None:
        return "application/pdf"

    @property
    @override
    def short_desc(self) -> str:
        url_desc = resolve_uri(self.url).kind.desc
        return f"{url_desc} of a PDF document"

    @override
    async def rendered_plain(self) -> str:
        return self.url

    @override
    async def rendered_html(self) -> str:
        template_source = '<a href="{{ url|e }}" class="msg-pdf">{{ url|e }}</a>'
        return await render_jinja2_async(
            template_source=template_source,
            template_category=TemplateCategory.HTML,
            templating_context={
                "url": self.url,
            },
        )

    @override
    async def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return f"[{self.url}]({self.url})"
