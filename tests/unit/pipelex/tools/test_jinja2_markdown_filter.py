import pytest

from pipelex.cogt.templating.template_rendering import render_template
from pipelex.tools.jinja2.exceptions import Jinja2TemplateRenderError
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async
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

    async def test_a_missing_value_prints_nothing_in_a_lenient_template(self) -> None:
        rendered = await render_jinja2_async(
            template_source="[{{ notes | markdown }}][{{ absent | markdown }}]",
            template_category=TemplateCategory.HTML,
            templating_context={"notes": None},
        )
        assert rendered == "[][]"

    async def test_a_missing_field_fails_in_a_strict_template(self) -> None:
        """A misspelled field reached through an alias, which no load-time check can follow, still fails at render."""
        with pytest.raises(Jinja2TemplateRenderError):
            await render_jinja2_async(
                template_source="{% set invoice = inv %}{{ invoice.notez | markdown }}",
                template_category=TemplateCategory.HTML,
                templating_context={"inv": {"notes": "Paid."}},
                is_undefined_strict=True,
            )
