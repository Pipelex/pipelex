from typing import ClassVar

from pipelex.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat


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
            inputs={"data": "Data"},
            output="RenderedText",
            template=TemplateBlueprint(
                template="Hello {{ data.name }}!",
                category=TemplateCategory.MARKDOWN,
                templating_style=TemplatingStyle(
                    tag_style=TagStyle.TICKS,
                    text_format=TextFormat.MARKDOWN,
                ),
                extra_context=None,
            ),
        ),
    )

    CONSTRUCT_COMPOSE = (
        "construct_compose",
        PipeComposeSpec.model_validate(
            {
                "pipe_code": "compose_sheet",
                "description": "Compose interview sheet",
                "inputs": {"analysis": "MatchAnalysis", "questions": "InterviewQuestion[]"},
                "output": "InterviewSheet",
                "construct": {
                    "score": {"from": "analysis.overall_score"},
                    "questions": {"from": "questions"},
                },
            }
        ),
        # Use model_validate to create the expected blueprint via the same validation path
        PipeComposeBlueprint.model_validate(
            {
                "description": "Compose interview sheet",
                "inputs": {"analysis": "MatchAnalysis", "questions": "InterviewQuestion[]"},
                "output": "InterviewSheet",
                "construct": {
                    "score": {"from": "analysis.overall_score"},
                    "questions": {"from": "questions"},
                },
            }
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeComposeSpec, PipeComposeBlueprint]]] = [
        SIMPLE_COMPOSE,
        CONSTRUCT_COMPOSE,
    ]
