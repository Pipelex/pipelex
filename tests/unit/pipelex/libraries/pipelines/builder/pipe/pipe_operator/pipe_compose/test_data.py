from typing import ClassVar

from pipelex.core.pipes.input_requirement_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.tools.templating.template_blueprint import TemplateBlueprint
from pipelex.tools.templating.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle, TextFormat


class PipeComposeTestCases:
    SIMPLE_COMPOSE = (
        "simple_compose",
        PipeComposeSpec(
            pipe_code="template_renderer",
            description="Render a template",
            inputs={"data": "Data"},
            output="RenderedText",
            template="Hello {{ data.name }}!",
            target_format="markdown",
        ),
        PipeComposeBlueprint(
            description="Render a template",
            inputs={"data": InputRequirementBlueprint(concept="Data")},
            output="RenderedText",
            type="PipeCompose",
            category="PipeOperator",
            template=TemplateBlueprint(
                source="Hello {{ data.name }}!",
                category=TemplateCategory.MARKDOWN,
                templating_style=TemplatingStyle(
                    tag_style=TagStyle.TICKS,
                    text_format=TextFormat.MARKDOWN,
                ),
                extra_context=None,
            ),
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeComposeSpec, PipeComposeBlueprint]]] = [
        SIMPLE_COMPOSE,
    ]
