from typing import Any

import pytest

from pipelex import log, pretty_print
from pipelex.hub import get_template_provider
from pipelex.tools.templating.jinja2_rendering import render_jinja2
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle, TagStyle, TextFormat
from tests.cases import Fruit, JINJA2TestCases

PLACE_HOLDER = "place_holder"


@pytest.mark.asyncio(loop_scope="class")
class TestRenderJinja2:
    @pytest.mark.parametrize("jinja2_name", JINJA2TestCases.JINJA2_NAME)
    @pytest.mark.parametrize("color", JINJA2TestCases.COLOR)
    async def test_render_jinja2_name_from_text(self, jinja2_name: str, color: str):
        temlating_context = {PLACE_HOLDER: color}
        prompting_style = PromptingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.MARKDOWN,
        )

        jinja2_text: str = await render_jinja2(
            template_category=Jinja2TemplateCategory.LLM_PROMPT,
            template_provider=get_template_provider(),
            temlating_context=temlating_context,
            jinja2_name=jinja2_name,
            jinja2=None,
            prompting_style=prompting_style,
        )
        pretty_print(jinja2_text, title="jinja2_text")

    @pytest.mark.parametrize("jinja2", JINJA2TestCases.JINJA2_FOR_ANY)
    @pytest.mark.parametrize("color", JINJA2TestCases.COLOR)
    async def test_render_jinja2_from_text(self, jinja2: str, color: str):
        temlating_context = {PLACE_HOLDER: color}
        prompting_style = PromptingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.MARKDOWN,
        )

        jinja2_text: str = await render_jinja2(
            template_category=Jinja2TemplateCategory.LLM_PROMPT,
            template_provider=get_template_provider(),
            temlating_context=temlating_context,
            jinja2_name=None,
            jinja2=jinja2,
            prompting_style=prompting_style,
        )
        pretty_print(jinja2_text, title="jinja2_text")

    @pytest.mark.parametrize("jinja2", JINJA2TestCases.JINJA2_FOR_ANY)
    @pytest.mark.parametrize("fruit", JINJA2TestCases.FRUIT)
    async def test_render_jinja2_from_specific_object(self, jinja2: str, fruit: Fruit):
        temlating_context = {PLACE_HOLDER: fruit}
        prompting_style = PromptingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.MARKDOWN,
        )

        jinja2_text: str = await render_jinja2(
            template_category=Jinja2TemplateCategory.LLM_PROMPT,
            template_provider=get_template_provider(),
            temlating_context=temlating_context,
            jinja2_name=None,
            jinja2=jinja2,
            prompting_style=prompting_style,
        )
        pretty_print(jinja2_text, title="jinja2_text")

    @pytest.mark.parametrize("jinja2", JINJA2TestCases.JINJA2_FOR_STUFF)
    @pytest.mark.parametrize("prompting_style", JINJA2TestCases.STYLE)
    @pytest.mark.parametrize(("topic", "any_object"), JINJA2TestCases.ANY_OBJECT)
    async def test_render_jinja2_from_any_object(self, jinja2: str, prompting_style: PromptingStyle, topic: str, any_object: Any):
        temlating_context = {PLACE_HOLDER: any_object}
        log.verbose(f"Rendering Jinja2 for '{topic}' with style '{prompting_style}'")
        jinja2_text: str = await render_jinja2(
            template_category=Jinja2TemplateCategory.LLM_PROMPT,
            template_provider=get_template_provider(),
            temlating_context=temlating_context,
            jinja2_name=None,
            jinja2=jinja2,
            prompting_style=prompting_style,
        )
        log.verbose(f"Jinja2 rendered Jinja2 for '{topic}' with style '{prompting_style}':\n{jinja2_text}")
        pretty_print(jinja2_text, title="jinja2_text")
