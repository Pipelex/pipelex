import json

from typing_extensions import override

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_sync


class HtmlContent(StuffContent):
    inner_html: str
    css_class: str

    @property
    @override
    def short_desc(self) -> str:
        return f"some html ({len(self.inner_html)} chars)"

    @override
    def __str__(self) -> str:
        return self.rendered_html()

    @override
    def rendered_plain(self) -> str:
        return self.inner_html

    @override
    def rendered_html(self) -> str:
        template_source = '<div class="{{ css_class|e }}">{{ inner_html | safe }}</div>'
        return render_jinja2_sync(
            template_source=template_source,
            template_category=TemplateCategory.HTML,
            templating_context={
                "inner_html": self.inner_html,
                "css_class": self.css_class,
            },
        )

    @override
    def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return self.inner_html

    @override
    def rendered_json(self) -> str:
        return json.dumps({"html": self.inner_html, "css_class": self.css_class})
