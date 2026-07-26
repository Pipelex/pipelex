from typing import Callable, cast

import pytest

from pipelex import pretty_print
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept, get_pipe_router
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose, PipeComposeOutput
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat
from tests.cases import JINJA2TestCases


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipeCompose:
    @pytest.mark.parametrize("template_source", JINJA2TestCases.JINJA2_FOR_ANY)
    async def test_pipe_compose_for_any(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        template_source: str,
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
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
            pipe=PipeFactory[PipeCompose].make_from_blueprint(
                domain_code="generic",
                pipe_code="adhoc_for_test_pipe_compose_for_any",
                blueprint=pipe_compose_blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
        )
        pipe_compose_output = cast("PipeComposeOutput", await get_pipe_router().run(pipe_job=pipe_job))
        rendered_text = pipe_compose_output.main_stuff_as_str
        pretty_print(rendered_text)

    async def test_escaped_dollar_renders_as_literal(
        self,
        job_metadata: JobMetadata,
        load_empty_library: Callable[[], None],
    ):
        """Regression: `$$amount` is an escaped literal `$amount` and must never interpolate.

        PipeCompose stores its template in authored form, so render rewrites sigils exactly
        once. When PipeCompose stored the already-preprocessed template, `render_template` ran
        `rewrite_template_sigils` a second time, resurrecting `$$amount` → `$amount` →
        `{{ amount|format() }}` and silently rendering the value of `amount` instead of the
        literal `$amount`.
        """
        load_empty_library()
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=TextContent(text="999"),
                name="amount",
            ),
        )
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeFactory[PipeCompose].make_from_blueprint(
                domain_code="generic",
                pipe_code="adhoc_escaped_dollar_literal",
                blueprint=PipeComposeBlueprint(
                    description="Escaped literal dollar must render literally, not interpolate",
                    template="Price token: $$amount",
                    output=NativeConceptCode.TEXT,
                ),
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
            job_metadata=job_metadata,
            working_memory=working_memory,
        )
        pipe_compose_output = cast("PipeComposeOutput", await get_pipe_router().run(pipe_job=pipe_job))
        rendered_text = pipe_compose_output.main_stuff_as_str
        pretty_print(rendered_text)
        assert "$amount" in rendered_text, "escaped `$$amount` must render as the literal `$amount`"
        assert "999" not in rendered_text, "escaped `$$amount` must not interpolate the value of `amount`"

    @pytest.mark.parametrize("template_source", JINJA2TestCases.JINJA2_FOR_STUFF)
    async def test_pipe_compose_for_stuff(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        template_source: str,
        load_empty_library: Callable[[], None],
    ):
        load_empty_library()
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=TextContent(text="[some text from test_pipe_compose_for_stuff]"),
                name="place_holder",
            ),
        )

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
            pipe=PipeFactory[PipeCompose].make_from_blueprint(
                domain_code="generic",
                pipe_code="adhoc_for_test_pipe_compose",
                blueprint=pipe_compose_blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
            working_memory=working_memory,
        )
        pipe_compose_output = cast("PipeComposeOutput", await get_pipe_router().run(pipe_job=pipe_job))
        rendered_text = pipe_compose_output.main_stuff_as_str
        pretty_print(rendered_text)
