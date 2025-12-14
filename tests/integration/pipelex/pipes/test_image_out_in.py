from pathlib import Path
from typing import Callable

import pytest

from pipelex.hub import get_pipe_router, get_required_pipe
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestImageOutIn:
    async def test_image_out_in(self, pipe_run_mode: PipeRunMode, load_test_library: Callable[[list[Path]], None]) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])
        # Create the page content
        # image_content = ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG)
        # image_content = ImageContent(url=f"file://{ImageTestCases.IMAGE_FILE_PATH_PNG_1}")
        # text_and_images = TextAndImagesContent(text=TextContent(text="It was designed by Slartibartfast, a famous designer"), images=[])
        # page_content = PageContent(text_and_images=text_and_images, page_view=image_content)

        # # Create stuff from page content
        # stuff = StuffFactory.make_stuff(
        #     concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.PAGE),
        #     content=page_content,
        #     name="page",
        # )

        # # Create working memory
        # working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Run the pipe
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="image_out_in"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                # working_memory=working_memory,
                job_metadata=JobMetadata(),
            ),
        )

        if pipe_run_mode != PipeRunMode.DRY:
            description = pipe_output.main_stuff_as_str
            assert description
