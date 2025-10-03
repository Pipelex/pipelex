from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle, TagStyle, TextFormat


class PipeComposeTestCases:
    SIMPLE_JINJA2 = (
        "simple_jinja2",
        PipeComposeSpec(
            pipe_code="template_renderer",
            description="Render a template",
            inputs={"data": "Data"},
            output="RenderedText",
            jinja2="Hello {{ data.name }}!",
            target_format="markdown",
        ),
        PipeComposeBlueprint(
            description="Render a template",
            inputs={"data": InputRequirementBlueprint(concept="Data")},
            output="RenderedText",
            type="PipeCompose",
            category="PipeOperator",
            jinja2_name=None,
            jinja2="Hello {{ data.name }}!",
            prompting_style=PromptingStyle(
                tag_style=TagStyle.TICKS,
                text_format=TextFormat.MARKDOWN,
            ),
            template_category=Jinja2TemplateCategory.MARKDOWN,
            extra_context=None,
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeComposeSpec, PipeComposeBlueprint]]] = [
        SIMPLE_JINJA2,
    ]
