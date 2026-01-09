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

    async def test_image_input_within_concept_without_filter(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that nested images are NOT included without the | with_images filter."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])
        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test that a pipe with nested images in input does NOT send images without | with_images filter",
            inputs={"page": "Page"},
            output="Text",
            prompt="Describe the page: @page",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_image_input_within_concept_without_filter",
            blueprint=pipe_llm_blueprint,
        )

        # Without | with_images filter, no images should be included (text-only rendering)
        assert pipe_llm.llm_prompt_spec.image_references is None

    async def test_image_input_within_concept_with_filter(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that nested images ARE included when using the | with_images filter."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])
        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test that a pipe with | with_images filter DOES send nested images",
            inputs={"page": "Page"},
            output="Text",
            prompt="Describe the page: {{ page | with_images }}",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_image_input_within_concept_with_filter",
            blueprint=pipe_llm_blueprint,
        )

        # With | with_images filter, images should be included as NESTED reference
        assert pipe_llm.llm_prompt_spec.image_references is not None
        assert len(pipe_llm.llm_prompt_spec.image_references) == 1
        image_ref = pipe_llm.llm_prompt_spec.image_references[0]
        assert image_ref.variable_path == "page"
        assert image_ref.kind.value == "nested"
        # Should have nested image paths
        assert image_ref.nested_image_paths is not None
        assert "text_and_images.images" in image_ref.nested_image_paths
        assert "page_view" in image_ref.nested_image_paths

    async def test_prompt_text_has_image_tokens_for_direct_image(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that prompt text contains [Image N] tokens, not image URLs, for direct Image input."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        # Create a pipe with direct Image input
        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test prompt text for direct image",
            inputs={"image": "Image"},
            output="Text",
            prompt="Describe this image: @image",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_prompt_text_direct_image",
            blueprint=pipe_llm_blueprint,
        )

        # Create working memory with an image
        image_url = ImageTestCases.IMAGE_FILE_PATH_PNG_1
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=ImageContent(url=image_url),
                name="image",
            ),
        )

        # Build the prompt
        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        # Verify prompt text contains [Image 1] token
        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text

        # Verify prompt text does NOT contain the image URL
        assert image_url not in llm_prompt.user_text
        assert "ai_lympics" not in llm_prompt.user_text

    async def test_prompt_text_has_image_tokens_for_image_list(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that prompt text contains [Image N] tokens, not image URLs, for Image[] input."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        # Create a pipe with Image[] input
        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test prompt text for image list",
            inputs={"images": "Image[]"},
            output="Text",
            prompt="Analyze these images: $images",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_prompt_text_image_list",
            blueprint=pipe_llm_blueprint,
        )

        # Create working memory with a list of images
        image_urls = [
            ImageTestCases.IMAGE_FILE_PATH_PNG_1,
            ImageTestCases.IMAGE_FILE_PATH_JPG_1,
        ]
        image_list = ListContent[ImageContent](items=[ImageContent(url=url) for url in image_urls])
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=image_list,
                name="images",
            ),
        )

        # Build the prompt
        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        # Verify prompt text contains [Image N] tokens
        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text
        assert "[Image 2]" in llm_prompt.user_text

        # Verify prompt text does NOT contain image URLs
        for image_url in image_urls:
            assert image_url not in llm_prompt.user_text
        assert "ai_lympics" not in llm_prompt.user_text
        assert "animal_lympics" not in llm_prompt.user_text

    async def test_prompt_text_has_image_tokens_for_multiple_image_lists(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that prompt text contains correct [Image N] tokens for multiple Image[] inputs."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        # Create a pipe with two Image[] inputs
        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test prompt text for multiple image lists",
            inputs={"collection_a": "Image[]", "collection_b": "Image[]"},
            output="Text",
            prompt="First: $collection_a\nSecond: $collection_b",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_prompt_text_multiple_lists",
            blueprint=pipe_llm_blueprint,
        )

        # Create working memory with two lists of images
        collection_a = ListContent[ImageContent](
            items=[
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_1),
            ]
        )
        collection_b = ListContent[ImageContent](
            items=[
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_2),
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_3),
            ]
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(
            stuff_list=[
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.IMAGE),
                    content=collection_a,
                    name="collection_a",
                ),
                StuffFactory.make_stuff(
                    concept=get_native_concept(NativeConceptCode.IMAGE),
                    content=collection_b,
                    name="collection_b",
                ),
            ],
        )

        # Build the prompt
        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        # Verify prompt text contains [Image N] tokens for all 4 images
        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text
        assert "[Image 2]" in llm_prompt.user_text
        assert "[Image 3]" in llm_prompt.user_text
        assert "[Image 4]" in llm_prompt.user_text

        # Verify prompt text does NOT contain any image URLs or filenames
        assert "ai_lympics" not in llm_prompt.user_text
        assert "animal_lympics" not in llm_prompt.user_text
        assert "solar_system" not in llm_prompt.user_text
        assert "eiffel_tower" not in llm_prompt.user_text
        assert ".png" not in llm_prompt.user_text
        assert ".jpg" not in llm_prompt.user_text

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

    @pytest.mark.parametrize(("_topic", "data_url"), ImageTestCases.DATA_URL_TEST_CASES)
    async def test_image_input_with_data_url(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
        _topic: str,
        data_url: str,
    ) -> None:
        """Test that ImageContent with data URL works as pipeline input.

        This test verifies that a data URL (data:image/png;base64,...) can be used
        as the URL in ImageContent and is correctly processed through the pipeline.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        # Create ImageContent with data URL
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=ImageContent(url=data_url),
                name="image",
            ),
        )

        # Run the extract_article_from_image pipe (which expects an Image input)
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="extract_article_from_image"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )

        # Verify the pipeline executed successfully
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None
