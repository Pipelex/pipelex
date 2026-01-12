import json

from typing_extensions import override

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_sync


class MermaidContent(StuffContent):
    mermaid_code: str
    mermaid_url: str

    @property
    @override
    def short_desc(self) -> str:
        return f"some mermaid code ({len(self.mermaid_code)} chars)"

    @override
    def __str__(self) -> str:
        return self.mermaid_code

    @override
    def rendered_plain(self) -> str:
        return self.mermaid_code

    @override
    def rendered_html(self) -> str:
        template_source = '<div class="mermaid">{{ mermaid_code|e }}</div>'
        return render_jinja2_sync(
            template_source=template_source,
            template_category=TemplateCategory.HTML,
            templating_context={
                "mermaid_code": self.mermaid_code,
            },
        )

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return self.mermaid_code

    @override
    def rendered_json(self) -> str:
        return json.dumps({"mermaid": self.mermaid_code})
