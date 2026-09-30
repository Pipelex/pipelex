from typing import Any, Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.interpreter_hub import get_pipe_library, get_pipe_router
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.runtime_hub import get_content_generator
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


@pytest.mark.asyncio(loop_scope="class")
class TestPipeLLMMarkdownOutputPath:
    async def test_markdown_output_takes_text_path(
        self,
        job_metadata: JobMetadata,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
    ) -> None:
        """`output = "Markdown"` is Text-compatible: the LLM writes free text, held in a MarkdownContent, never an object."""
        load_empty_library()
        content_generator = get_content_generator()
        make_llm_text_spy = mocker.spy(content_generator, "make_llm_text")
        make_object_spy = mocker.spy(content_generator, "make_object")

        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="building_inspections",
            pipe_code="adhoc_markdown_output_path",
            blueprint=PipeLLMBlueprint(
                description="Write site notes up as an inspection report in Markdown",
                output=NativeConceptCode.MARKDOWN,
                prompt="Write the inspection report in Markdown, with a heading for each area inspected.",
            ),
        )
        get_pipe_library().add_new_pipe(pipe)

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
            job_metadata=job_metadata,
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        make_llm_text_spy.assert_called_once()
        make_object_spy.assert_not_called()

        main_stuff = pipe_output.main_stuff
        assert main_stuff.concept.concept_ref == NativeConceptCode.MARKDOWN.concept_ref
        content: Any = main_stuff.content
        assert type(content) is MarkdownContent
        assert content.text
        assert pipe_output.main_stuff_as_markdown.text == content.text
