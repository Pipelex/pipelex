from typing import TYPE_CHECKING, cast

import pytest

from pipelex import pretty_print
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TagStyle, TemplatingStyle, TextFormat
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import get_pipe_router
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_operators.compose.pipe_compose_factory import PipeComposeFactory
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from tests.cases import JINJA2TestCases

if TYPE_CHECKING:
    from pipelex.pipe_operators.compose.pipe_compose import PipeComposeOutput


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeCompose:
    @pytest.mark.parametrize("template_source", JINJA2TestCases.JINJA2_FOR_ANY)
    async def test_pipe_compose_for_any(
        self,
        pipe_run_mode: PipeRunMode,
        template_source: str,
    ):
        pipe_compose_blueprint = PipeComposeBlueprint(
            description="Jinja2 test for any context",
            template=TemplateBlueprint(
                template=template_source,
                templating_style=TemplatingStyle(tag_style=TagStyle.TICKS, text_format=TextFormat.MARKDOWN),
                category=TemplateCategory.MARKDOWN,
                extra_context={"place_holder": "[some text from test_pipe_compose_for_any]"},
            ),
            output=NativeConceptCode.TEXT,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeComposeFactory.make_from_blueprint(
                domain="generic",
                pipe_code="adhoc_for_test_pipe_compose_for_any",
                blueprint=pipe_compose_blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_compose_output = cast("PipeComposeOutput", await get_pipe_router().run(pipe_job=pipe_job))
        rendered_text = pipe_compose_output.main_stuff_as_str
        pretty_print(rendered_text)

    @pytest.mark.parametrize("template_source", JINJA2TestCases.JINJA2_FOR_STUFF)
    async def test_pipe_compose_for_stuff(
        self,
        pipe_run_mode: PipeRunMode,
        template_source: str,
    ):
        working_memory = WorkingMemoryFactory.make_from_text(text="[some text from test_pipe_compose_for_stuff]", name="place_holder")

        pipe_compose_blueprint = PipeComposeBlueprint(
            description="Jinja2 test for stuff context",
            template=TemplateBlueprint(
                template=template_source,
                templating_style=TemplatingStyle(tag_style=TagStyle.TICKS, text_format=TextFormat.MARKDOWN),
                category=TemplateCategory.MARKDOWN,
                extra_context={"place_holder": "[some text from test_pipe_compose_for_stuff]"},
            ),
            output=NativeConceptCode.TEXT,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeComposeFactory.make_from_blueprint(
                domain="generic",
                pipe_code="adhoc_for_test_pipe_compose",
                blueprint=pipe_compose_blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            working_memory=working_memory,
        )
        pipe_compose_output = cast("PipeComposeOutput", await get_pipe_router().run(pipe_job=pipe_job))
        rendered_text = pipe_compose_output.main_stuff_as_str
        pretty_print(rendered_text)
