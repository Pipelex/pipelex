import pytest

from pipelex import pretty_print
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.hub import get_pipe_router
from pipelex.pipe_operators.pipe_template import PipeTemplate, PipeTemplateOutput
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from pipelex.tools.templating.templating_models import PromptingStyle, TagStyle, TextFormat
from tests.cases import TemplateTestCases


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeJinja2:
    @pytest.mark.parametrize("template", TemplateTestCases.TEMPLATE_FOR_ANY)
    async def test_pipe_template_for_any(
        self,
        pipe_run_mode: PipeRunMode,
        template: str,
    ):
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeTemplate(
                code="adhoc_for_test_pipe_template_for_any",
                domain="generic",
                template=template,
                extra_context={"place_holder": "[some text from test_pipe_template_for_any]"},
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )
        pipe_template_output: PipeTemplateOutput = await get_pipe_router().run_pipe_job(pipe_job=pipe_job)
        rendered_text = pipe_template_output.rendered_text
        pretty_print(rendered_text)

    @pytest.mark.parametrize("template", TemplateTestCases.TEMPLATE_FOR_STUFF)
    async def test_pipe_template_for_stuff(
        self,
        pipe_run_mode: PipeRunMode,
        template: str,
    ):
        working_memory = WorkingMemoryFactory.make_from_text(text="[some text from test_pipe_template_for_stuff]", name="place_holder")

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeTemplate(
                code="adhoc_for_test_pipe_template",
                domain="generic",
                template=template,
                prompting_style=PromptingStyle(tag_style=TagStyle.TICKS, text_format=TextFormat.MARKDOWN),
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            working_memory=working_memory,
        )
        pipe_template_output: PipeTemplateOutput = await get_pipe_router().run_pipe_job(pipe_job=pipe_job)
        rendered_text = pipe_template_output.rendered_text
        pretty_print(rendered_text)
