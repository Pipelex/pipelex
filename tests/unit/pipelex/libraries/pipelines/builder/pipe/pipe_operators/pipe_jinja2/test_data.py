"""
Test data for PipeJinja2Blueprint conversion tests.
"""

from typing import ClassVar, List, Tuple

from pipelex.core.pipes.pipe_input_spec_blueprint import (
    InputRequirementBlueprint as InputRequirementBlueprintCore,
)
from pipelex.libraries.pipelines.builder.pipe.inputs import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_jinja2_builder import PipeJinja2Blueprint, PromptingStyle
from pipelex.pipe_operators.jinja2.pipe_jinja2_blueprint import (
    PipeJinja2Blueprint as PipeJinja2BlueprintCore,
)
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle as PromptingStyleCore
from pipelex.tools.templating.templating_models import TagStyle, TextFormat


class PipeJinja2TestCases:
    """Test cases for PipeJinja2Blueprint conversion."""

    SIMPLE_JINJA2 = (
        "simple_jinja2",
        PipeJinja2Blueprint(
            definition="Render a template",
            inputs={"data": InputRequirementBlueprint(concept="Data")},
            output="RenderedText",
            jinja2="Hello {{ data.name }}!",
        ),
        "template_renderer",
        "test_domain",
        PipeJinja2BlueprintCore(
            definition="Render a template",
            inputs={"data": InputRequirementBlueprintCore(concept="Data")},
            output="RenderedText",
            type="PipeJinja2",
            category="PipeOperator",
            jinja2_name=None,
            jinja2="Hello {{ data.name }}!",
            prompting_style=None,
            template_category=Jinja2TemplateCategory.LLM_PROMPT,
            extra_context=None,
        ),
    )

    JINJA2_WITH_STYLE = (
        "jinja2_with_style",
        PipeJinja2Blueprint(
            definition="Template with prompting style",
            inputs={"input": InputRequirementBlueprint(concept="Input")},
            output="Output",
            jinja2_name="custom_template",
            prompting_style=PromptingStyle(
                tag_style=TagStyle.XML,
                text_format=TextFormat.MARKDOWN,
            ),
            template_category=Jinja2TemplateCategory.MARKDOWN,
            extra_context={"version": "1.0"},
        ),
        "styled_template",
        "test_domain",
        PipeJinja2BlueprintCore(
            definition="Template with prompting style",
            inputs={"input": InputRequirementBlueprintCore(concept="Input")},
            output="Output",
            type="PipeJinja2",
            category="PipeOperator",
            jinja2_name="custom_template",
            jinja2=None,
            prompting_style=PromptingStyleCore(
                tag_style=TagStyle.XML,
                text_format=TextFormat.MARKDOWN,
            ),
            template_category=Jinja2TemplateCategory.MARKDOWN,
            extra_context={"version": "1.0"},
        ),
    )

    TEST_CASES: ClassVar[List[Tuple[str, PipeJinja2Blueprint, str, str, PipeJinja2BlueprintCore]]] = [
        SIMPLE_JINJA2,
        JINJA2_WITH_STYLE,
    ]
