from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.inputs_spec import InputRequirementSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_jinja2_spec import PipeJinja2Spec, PromptingStyleSpec
from pipelex.pipe_operators.jinja2.pipe_jinja2_blueprint import PipeJinja2Blueprint
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle, TagStyle, TextFormat


class PipeJinja2TestCases:
    SIMPLE_JINJA2 = (
        "simple_jinja2",
        PipeJinja2Spec(
            the_pipe_code="template_renderer",
            definition="Render a template",
            inputs={"data": InputRequirementSpec(concept="Data")},
            output="RenderedText",
            jinja2="Hello {{ data.name }}!",
        ),
        PipeJinja2Blueprint(
            definition="Render a template",
            inputs={"data": InputRequirementBlueprint(concept="Data")},
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
        PipeJinja2Spec(
            the_pipe_code="styled_template",
            definition="Template with prompting style",
            inputs={"input": InputRequirementSpec(concept="Input")},
            output="Output",
            jinja2_name="custom_template",
            prompting_style=PromptingStyleSpec(
                tag_style=TagStyle.XML,
                text_format=TextFormat.MARKDOWN,
            ),
            template_category=Jinja2TemplateCategory.MARKDOWN,
            extra_context={"version": "1.0"},
        ),
        PipeJinja2Blueprint(
            definition="Template with prompting style",
            inputs={"input": InputRequirementBlueprint(concept="Input")},
            output="Output",
            type="PipeJinja2",
            category="PipeOperator",
            jinja2_name="custom_template",
            jinja2=None,
            prompting_style=PromptingStyle(
                tag_style=TagStyle.XML,
                text_format=TextFormat.MARKDOWN,
            ),
            template_category=Jinja2TemplateCategory.MARKDOWN,
            extra_context={"version": "1.0"},
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeJinja2Spec, PipeJinja2Blueprint]]] = [
        SIMPLE_JINJA2,
        JINJA2_WITH_STYLE,
    ]
