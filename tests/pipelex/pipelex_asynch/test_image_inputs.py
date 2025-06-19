from typing import cast

import pytest
from pytest import FixtureRequest

from pipelex import pretty_print
from pipelex.core.pipe_abstract import PipeAbstract
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuff_content import ImageContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import get_report_delegate, get_required_pipe
from pipelex.pipeline.job_metadata import JobMetadata
from tests.test_data import ImageTestCases
from tests.test_pipelines.misc_tests.tests import Article


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestImageInputs:
    """Test class for verifying image input functionality in pipes."""

    async def test_page_content_input(self, request: FixtureRequest) -> None:
        """Test that a pipe can accept a PageContent input.

        Args:
            request: Pytest fixture request object for accessing test metadata.
        """
        # Create the page content
        image_content = ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG)

        # Create stuff from page content
        stuff = StuffFactory.make_stuff(concept_str="Image", content=image_content, name="image")

        # Create working memory
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Get the pipe
        pipe: PipeAbstract = get_required_pipe(pipe_code="describe_page_content_test")

        # Run the pipe
        pipe_output: PipeOutput = await pipe.run_pipe(
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
            working_memory=working_memory,
            job_metadata=JobMetadata(
                top_job_id=cast(str, request.node.originalname),  # type: ignore
            ),
        )

        # Log output and generate report
        pretty_print(pipe_output, title="Pipe output")
        get_report_delegate().generate_report()

        article = pipe_output.main_stuff_as(content_type=Article)
        pretty_print(article, title="Article")
        # Verify output
        assert article.title == "The Solar System: An Overview"
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None
        assert pipe_output.main_stuff.concept_code == "test_image_inputs.Article"
