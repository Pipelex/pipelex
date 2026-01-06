import json

from typing_extensions import override

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async


class HtmlContent(StuffContent):
    inner_html: str
    css_class: str

    @property
    @override
    def short_desc(self) -> str:
        return f"some html ({len(self.inner_html)} chars)"

    # @override
    # def __str__(self) -> str:
    #     return asyncio.run(self.rendered_html())

    @override
    async def rendered_plain(self) -> str:
        return self.inner_html

    @override
    async def rendered_html(self) -> str:
        template_source = '<div class="{{ css_class|e }}">{{ inner_html | safe }}</div>'
        return await render_jinja2_async(
            template_source=template_source,
            template_category=TemplateCategory.HTML,
            temlating_context={
                "inner_html": self.inner_html,
                "css_class": self.css_class,
            },
        )

    @override
    async def rendered_markdown(self, level: int = 1, is_pretty: bool = False) -> str:
        return self.inner_html

    @override
    async def rendered_json(self) -> str:
        return json.dumps({"html": self.inner_html, "css_class": self.css_class})
