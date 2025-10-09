from typing import Any

import pytest

from pipelex import log, pretty_print
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TagStyle, TemplatingStyle, TextFormat
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2
from tests.cases import Fruit, JINJA2TestCases

PLACE_HOLDER = "place_holder"


@pytest.mark.asyncio(loop_scope="class")
class TestRenderJinja2:
    @pytest.mark.parametrize("template", JINJA2TestCases.JINJA2_FOR_ANY)
    @pytest.mark.parametrize("color", JINJA2TestCases.COLOR)
    async def test_render_jinja2_from_text(self, template: str, color: str):
        temlating_context = {PLACE_HOLDER: color}
        templating_style = TemplatingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.MARKDOWN,
        )

        jinja2_text: str = await render_jinja2(
            template_category=TemplateCategory.LLM_PROMPT,
            temlating_context=temlating_context,
            template_source=template,
            templating_style=templating_style,
        )
        pretty_print(jinja2_text, title="jinja2_text")

    @pytest.mark.parametrize("template", JINJA2TestCases.JINJA2_FOR_ANY)
    @pytest.mark.parametrize("fruit", JINJA2TestCases.FRUIT)
    async def test_render_jinja2_from_specific_object(self, template: str, fruit: Fruit):
        temlating_context = {PLACE_HOLDER: fruit}
        templating_style = TemplatingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.MARKDOWN,
        )

        jinja2_text: str = await render_jinja2(
            template_category=TemplateCategory.LLM_PROMPT,
            temlating_context=temlating_context,
            template_source=template,
            templating_style=templating_style,
        )
        pretty_print(jinja2_text, title="jinja2_text")

    @pytest.mark.parametrize("template", JINJA2TestCases.JINJA2_FOR_STUFF)
    @pytest.mark.parametrize("templating_style", JINJA2TestCases.STYLE)
    @pytest.mark.parametrize(("topic", "any_object"), JINJA2TestCases.ANY_OBJECT)
    async def test_render_jinja2_from_any_object(self, template: str, templating_style: TemplatingStyle, topic: str, any_object: Any):
        temlating_context = {PLACE_HOLDER: any_object}
        log.verbose(f"Rendering Jinja2 for '{topic}' with style '{templating_style}'")
        jinja2_text: str = await render_jinja2(
            template_category=TemplateCategory.LLM_PROMPT,
            temlating_context=temlating_context,
            template_source=template,
            templating_style=templating_style,
        )
        log.verbose(f"Jinja2 rendered Jinja2 for '{topic}' with style '{templating_style}':\n{jinja2_text}")
        pretty_print(jinja2_text, title="jinja2_text")
