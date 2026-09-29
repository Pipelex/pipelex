import pytest

from pipelex.cogt.templating.template_rendering import render_template
from pipelex.tools.jinja2.template_category import TemplateCategory


@pytest.mark.asyncio
class TestMarkdownFilter:
    async def test_the_filter_turns_markdown_into_html_in_an_html_template(self) -> None:
        rendered = await render_template("<div>{{ notes | markdown }}</div>", category=TemplateCategory.HTML, context={"notes": "**Paid** in full."})
        assert rendered == "<div><p><strong>Paid</strong> in full.</p>\n</div>"

    async def test_raw_html_in_the_source_is_shown_as_text(self) -> None:
        rendered = await render_template("{{ notes | markdown }}", category=TemplateCategory.HTML, context={"notes": "<script>alert(1)</script>"})
        assert "<script>" not in rendered
        assert "&lt;script&gt;" in rendered
