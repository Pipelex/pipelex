from typing_extensions import override

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_sync
from pipelex.tools.misc.path_utils import interpret_path_or_url


class PDFContent(StuffContent):
    url: str

    @property
    @override
    def short_desc(self) -> str:
        url_desc = interpret_path_or_url(path_or_uri=self.url).desc
        return f"{url_desc} of a PDF document"

    @override
    def rendered_plain(self) -> str:
        return self.url

    @override
    def rendered_html(self) -> str:
        template_source = '<a href="{{ url|e }}" class="msg-pdf">{{ url|e }}</a>'
        return render_jinja2_sync(
            template_source=template_source,
            template_category=TemplateCategory.HTML,
            temlating_context={
                "url": self.url,
            },
        )

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return f"[{self.url}]({self.url})"
