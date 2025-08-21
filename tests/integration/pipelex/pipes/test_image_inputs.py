import pytest
from pytest import FixtureRequest

from pipelex import pretty_print
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff_content import ImageContent, PageContent, TextAndImagesContent, TextContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_pipe_router, get_report_delegate
from pipelex.pipeline.job_metadata import JobMetadata
from tests.cases import ImageTestCases
from tests.test_pipelines.misc_tests.test_structures import Article


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestImageInputs:
    """Test class for verifying image input functionality in pipes."""

    async def test_extract_article_from_image(
        self,
        request: FixtureRequest,
        pipe_run_mode: PipeRunMode,
    ) -> None:
        """Test that an image is indeed given to the LLM, and that it can extract extact whats on the image."""
        working_memory = WorkingMemoryFactory.make_from_image(name="image", image_url=ImageTestCases.IMAGE_FILE_PATH_PNG)

        # Run the pipe
        pipe_output: PipeOutput = await get_pipe_router().run_pipe_code(
            pipe_code="extract_article_from_image",
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            working_memory=working_memory,
            job_metadata=JobMetadata(job_name=request.node.originalname),  # type: ignore
        )

        # Log output and generate report
        pretty_print(pipe_output, title="Pipe output")
        get_report_delegate().generate_report()

        # Verify output
        if pipe_run_mode != PipeRunMode.DRY:
            article = pipe_output.main_stuff_as(content_type=Article)
            assert article.title == "2037 AI-Lympics"
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

    async def test_describe_page(self, request: FixtureRequest, pipe_run_mode: PipeRunMode) -> None:
        """
        Test that a pipe can accept a PageContent input, give to the LLM the image via subattributes,
        But also accepts basic objects
        """
        # Create the page content
        image_content = ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG)
        text_and_images = TextAndImagesContent(text=TextContent(text="This is a test page"), images=[])
        page_content = PageContent(text_and_images=text_and_images, page_view=image_content)

        # Create stuff from page content
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.PAGE]),
            content=page_content,
            name="page",
        )

        # Create working memory
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Run the pipe
        pipe_output: PipeOutput = await get_pipe_router().run_pipe_code(
            pipe_code="describe_page",
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            working_memory=working_memory,
            job_metadata=JobMetadata(job_name=request.node.originalname),  # type: ignore
        )

        # Log output and generate report
        pretty_print(pipe_output, title="Pipe output")
        get_report_delegate().generate_report()

        # Verify output
        if pipe_run_mode != PipeRunMode.DRY:
            article = pipe_output.main_stuff_as(content_type=Article)
            pretty_print(article, title="Article")
            assert article.title == "2037 AI-Lympics"
            assert article.description == "This is a test page"
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None
