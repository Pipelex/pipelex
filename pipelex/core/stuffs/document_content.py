from typing_extensions import override

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_sync
from pipelex.tools.uri.uri_resolver import resolve_uri


class DocumentContent(StuffContent):
    url: str
    mime_type: str | None = None
    display_link: str | None = None

    @property
    @override
    def content_type(self) -> str | None:
        return self.mime_type or "application/pdf"

    @property
    @override
    def short_desc(self) -> str:
        url_desc = resolve_uri(self.url).kind.desc
        return f"{url_desc} of a document"

    @override
    def rendered_plain(self) -> str:
        return self.url

    @override
    def rendered_html(self) -> str:
        # The |e filter escapes HTML special characters to prevent XSS attacks
        template_source = '<a href="{{ url|e }}" class="msg-document">{{ display_text|e }}</a>'
        return render_jinja2_sync(
            template_source=template_source,
            template_category=TemplateCategory.HTML,
            templating_context={
                "url": self.url,
                "display_text": self.display_link or self.url,
            },
        )

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        display_text = self.display_link or self.url
        return f"[{display_text}]({self.url})"
