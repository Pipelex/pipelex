"""End-to-end inference tests for image inputs."""

from pathlib import Path
from typing import Callable

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_native_concept, get_pipe_router, get_required_pipe
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.cases import ImageTestCases
from tests.integration.pipelex.pipes.pipelines.test_structures import Article


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestImageInputsInference:
    """End-to-end inference tests for image inputs."""

    async def test_extract_article_from_single_image(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test extracting article from a single image."""
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

        assert pipe_output is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode.is_live:
            article = pipe_output.main_stuff_as(content_type=Article)
            title_lower = article.title.lower()
            assert "ai-lympics" in title_lower or "ai-olympics" in title_lower or "ailympics" in title_lower
            location_lower = article.location.lower()
            assert "paris" in location_lower or "paris, france" in location_lower
            assert article.year == 2037

    async def test_describe_page_with_nested_images(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test describing a page with nested images."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        image_content = ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1)
        text_and_images = TextAndImagesContent(
            text=TextContent(text="It was designed by Slartibartfast, a famous designer"),
            images=[],
        )
        page_content = PageContent(text_and_images=text_and_images, page_view=image_content)

        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.PAGE),
            content=page_content,
            name="page",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="describe_page"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )

        assert pipe_output is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode.is_live:
            article = pipe_output.main_stuff_as(content_type=Article)
            title_lower = article.title.lower()
            assert "ai-lympics" in title_lower or "ai-olympics" in title_lower or "ailympics" in title_lower
            location_lower = article.location.lower()
            assert "paris" in location_lower or "paris, france" in location_lower
            assert article.year == 2037
            assert "slartibartfast" in article.description.lower()

    async def test_analyze_image_collection(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test analyzing a collection of images (Image[] input)."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        image_contents = [
            ImageContent(url=f"{ImageTestCases.IMAGE_FILE_PATH_PNG_1}"),
            ImageContent(url=f"{ImageTestCases.IMAGE_FILE_PATH_JPG_1}"),
            ImageContent(url=f"{ImageTestCases.IMAGE_FILE_PATH_JPG_3}"),
        ]
        image_list_content = ListContent[ImageContent](items=image_contents)

        image_collection_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=image_list_content,
            name="collection_of_images",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=image_collection_stuff)

        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="analyze_image_collection"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )

        assert pipe_output is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode.is_live:
            # Verify that the output is the Analysis concept from the MTHDS file
            assert pipe_output.main_stuff.concept.code == "Analysis"

    async def test_compare_two_image_collections(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test comparing two image collections (multiple Image[] inputs)."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

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

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(
            stuff_list=[collection_a_stuff, collection_b_stuff],
        )

        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="compare_two_image_collections"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )

        assert pipe_output is not None
        assert pipe_output.main_stuff is not None

        if pipe_run_mode.is_live:
            # Verify that the output is the Analysis concept from the MTHDS file
            assert pipe_output.main_stuff.concept.code == "Analysis"

    @pytest.mark.parametrize(("_topic", "data_url"), ImageTestCases.DATA_URL_VISION_TEST_CASES)
    async def test_image_input_with_data_url(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        _topic: str,
        data_url: str,
    ) -> None:
        """Test that data URL images work as pipeline input."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=ImageContent(url=data_url),
                name="image",
            ),
        )

        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="describe_image"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )

        assert pipe_output is not None
        assert pipe_output.main_stuff is not None
