from pathlib import Path
from typing import Callable

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_native_concept, get_pipe_router, get_required_pipe
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.cases import ImageTestCases
from tests.integration.pipelex.pipes.pipelines.test_structures import Article


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestImageInputs:
    """Test class for verifying image input functionality in pipes."""

    async def test_extract_article_from_image(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
                name="image",
            ),
        )

        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="extract_article_from_image"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )
        if pipe_run_mode != PipeRunMode.DRY:
            article = pipe_output.main_stuff_as(content_type=Article)
            assert article.title in {
                "2037 AI-Lympics Paris",
                "2037 AI-Lympics PARIS",
                "2037 AI-Lympics",
                "2037 AI-LYMPICS PARIS",
                "2037 AI-LYMPICS",
            }
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

    async def test_describe_page(
        self, job_metadata: JobMetadata, pipe_run_mode: PipeRunMode, load_test_library: Callable[[list[Path]], None]
    ) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])
        # Create the page content
        # image_content = ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG)
        image_content = ImageContent(url=f"file://{ImageTestCases.IMAGE_FILE_PATH_PNG_1}")
        text_and_images = TextAndImagesContent(text=TextContent(text="It was designed by Slartibartfast, a famous designer"), images=[])
        page_content = PageContent(text_and_images=text_and_images, page_view=image_content)

        # Create stuff from page content
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.PAGE),
            content=page_content,
            name="page",
        )

        # Create working memory
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Run the pipe
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="describe_page"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )

        if pipe_run_mode != PipeRunMode.DRY:
            article = pipe_output.main_stuff_as(content_type=Article)
            assert article.title in {
                "2037 AI-Lympics Paris",
                "2037 AI-Lympics PARIS",
                "2037 AI-Lympics",
                "2037 AI-LYMPICS PARIS",
                "2037 AI-LYMPICS",
            }
            assert article.description == "This is the description of the page blablabla"
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

    @pytest.mark.usefixtures("request")
    async def test_image_input_within_concept_with_text(self, load_test_library: Callable[[list[Path]], None]) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])
        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test that a pipe can accept a PageContent input, give to the LLM the image via subattributes",
            inputs={"page": "Page"},
            output="Text",
            prompt="Describe the page: @page",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_image_input_within_concept_with_text",
            blueprint=pipe_llm_blueprint,
        )

        # Should find both the list of images in text_and_images and the single page_view image
        assert pipe_llm.llm_prompt_spec.user_images == ["page.text_and_images.images", "page.page_view"]

    async def test_analyze_image_collection(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test that a PipeLLM can process a ListContent of images (Image[] input)."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        # Create 3 images for the collection
        image_contents = [
            ImageContent(url=f"{ImageTestCases.IMAGE_FILE_PATH_PNG_1}"),
            ImageContent(url=f"{ImageTestCases.IMAGE_FILE_PATH_JPG_1}"),
            ImageContent(url=f"{ImageTestCases.IMAGE_FILE_PATH_JPG_3}"),
        ]

        # Create a ListContent containing the images
        image_list_content = ListContent[ImageContent](items=image_contents)

        # Create a stuff with the list of images
        image_collection_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=image_list_content,
            name="collection_of_images",
        )

        # Create working memory with the image collection
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=image_collection_stuff)

        # Run the pipe
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="analyze_image_collection"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )

        # Verify the output
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode != PipeRunMode.DRY:
            # Verify that the output is the Analysis concept from the PLX file
            assert pipe_output.main_stuff.concept.code == "Analysis"
            # Verify the content is some kind of text output (analysis result)
            assert pipe_output.main_stuff.content is not None

    async def test_compare_two_image_collections(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test that a PipeLLM can process two ListContent of images (Image[] inputs)."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        # Create collection_a with 2 images
        collection_a_images = [
            ImageContent(url=f"{ImageTestCases.IMAGE_FILE_PATH_PNG_1}"),
            ImageContent(url=f"{ImageTestCases.IMAGE_FILE_PATH_JPG_1}"),
        ]
        collection_a_list_content = ListContent[ImageContent](items=collection_a_images)
        collection_a_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=collection_a_list_content,
            name="collection_a",
        )

        # Create collection_b with 2 images
        collection_b_images = [
            ImageContent(url=f"{ImageTestCases.IMAGE_FILE_PATH_JPG_2}"),
            ImageContent(url=f"{ImageTestCases.IMAGE_FILE_PATH_JPG_3}"),
        ]
        collection_b_list_content = ListContent[ImageContent](items=collection_b_images)
        collection_b_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=collection_b_list_content,
            name="collection_b",
        )

        # Create working memory with both image collections
        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(
            stuff_list=[collection_a_stuff, collection_b_stuff],
        )

        # Run the pipe
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="compare_two_image_collections"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )

        # Verify the output
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode != PipeRunMode.DRY:
            # Verify that the output is the Analysis concept from the PLX file
            assert pipe_output.main_stuff.concept.code == "Analysis"
            # Verify the content is some kind of text output (analysis result)
            assert pipe_output.main_stuff.content is not None
