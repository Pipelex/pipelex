from typing import Any

import pytest

from pipelex import log, pretty_print
from pipelex.hub import get_template_provider
from pipelex.tools.templating.template_category import TemplateCategory
from pipelex.tools.templating.template_rendering import render_template
from pipelex.tools.templating.templating_models import PromptingStyle, TagStyle, TextFormat
from tests.cases import Fruit, TemplateTestCases

PLACE_HOLDER = "place_holder"


@pytest.mark.asyncio(loop_scope="class")
class TestRenderTemplate:
    @pytest.mark.parametrize("template_name", TemplateTestCases.TEMPLATE_NAME)
    @pytest.mark.parametrize("color", TemplateTestCases.COLOR)
    async def test_render_template_name_from_text(self, template_name: str, color: str):
        temlating_context = {PLACE_HOLDER: color}
        prompting_style = PromptingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.MARKDOWN,
        )

        template_text: str = await render_template(
            template_category=TemplateCategory.LLM_PROMPT,
            template_provider=get_template_provider(),
            temlating_context=temlating_context,
            template_name=template_name,
            template=None,
            prompting_style=prompting_style,
        )
        pretty_print(template_text, title="template_text")

    @pytest.mark.parametrize("template", TemplateTestCases.TEMPLATE_FOR_ANY)
    @pytest.mark.parametrize("color", TemplateTestCases.COLOR)
    async def test_render_template_from_text(self, template: str, color: str):
        temlating_context = {PLACE_HOLDER: color}
        prompting_style = PromptingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.MARKDOWN,
        )

        template_text: str = await render_template(
            template_category=TemplateCategory.LLM_PROMPT,
            template_provider=get_template_provider(),
            temlating_context=temlating_context,
            template_name=None,
            template=template,
            prompting_style=prompting_style,
        )
        pretty_print(template_text, title="template_text")

    @pytest.mark.parametrize("template", TemplateTestCases.TEMPLATE_FOR_ANY)
    @pytest.mark.parametrize("fruit", TemplateTestCases.FRUIT)
    async def test_render_template_from_specific_object(self, template: str, fruit: Fruit):
        temlating_context = {PLACE_HOLDER: fruit}
        prompting_style = PromptingStyle(
            tag_style=TagStyle.NO_TAG,
            text_format=TextFormat.MARKDOWN,
        )

        template_text: str = await render_template(
            template_category=TemplateCategory.LLM_PROMPT,
            template_provider=get_template_provider(),
            temlating_context=temlating_context,
            template_name=None,
            template=template,
            prompting_style=prompting_style,
        )
        pretty_print(template_text, title="template_text")

    @pytest.mark.parametrize("template", TemplateTestCases.TEMPLATE_FOR_STUFF)
    @pytest.mark.parametrize("prompting_style", TemplateTestCases.STYLE)
    @pytest.mark.parametrize("topic, any_object", TemplateTestCases.ANY_OBJECT)
    async def test_render_template_from_any_object(self, template: str, prompting_style: PromptingStyle, topic: str, any_object: Any):
        temlating_context = {PLACE_HOLDER: any_object}
        log.verbose(f"Rendering template for '{topic}' with style '{prompting_style}'")
        template_text: str = await render_template(
            template_category=TemplateCategory.LLM_PROMPT,
            template_provider=get_template_provider(),
            temlating_context=temlating_context,
            template_name=None,
            template=template,
            prompting_style=prompting_style,
        )
        log.verbose(f"Rendered template for '{topic}' with style '{prompting_style}':\n{template_text}")
        pretty_print(template_text, title="template_text")
