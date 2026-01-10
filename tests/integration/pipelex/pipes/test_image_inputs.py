"""Integration tests for image inputs in LLM prompts.

This module tests the complete flow of image handling in PipeLLM:
1. Factory-level: ImageReference creation from blueprints
2. Runtime: Prompt building with token substitution
3. Inference: End-to-end tests with actual LLM calls
"""

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
from pipelex.pipe_operators.llm.image_reference import ImageReferenceKind
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.cases import ImageTestCases
from tests.integration.pipelex.pipes.pipelines.test_structures import Article

# =============================================================================
# Factory-Level Tests: ImageReference Creation
# =============================================================================


@pytest.mark.dry_runnable
class TestImageReferencesFactoryLevel:
    """Tests for ImageReference creation at factory time (PipeFactory.make_from_blueprint)."""

    def test_direct_image_creates_direct_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Image input creates a DIRECT reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test DIRECT reference",
            inputs={"image": "Image"},
            output="Text",
            prompt="Describe: @image",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_direct_reference",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.image_references is not None
        assert len(pipe_llm.llm_prompt_spec.image_references) == 1
        ref = pipe_llm.llm_prompt_spec.image_references[0]
        assert ref.kind == ImageReferenceKind.DIRECT
        assert ref.variable_path == "image"

    def test_image_list_creates_direct_list_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Image[] input creates a DIRECT_LIST reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test DIRECT_LIST reference",
            inputs={"images": "Image[]"},
            output="Text",
            prompt="Analyze: $images",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_direct_list_reference",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.image_references is not None
        assert len(pipe_llm.llm_prompt_spec.image_references) == 1
        ref = pipe_llm.llm_prompt_spec.image_references[0]
        assert ref.kind == ImageReferenceKind.DIRECT_LIST
        assert ref.variable_path == "images"

    def test_nested_image_without_filter_no_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that struct with nested images WITHOUT | with_images creates NO reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test no reference without filter",
            inputs={"page": "Page"},
            output="Text",
            prompt="Describe the page: @page",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_no_reference",
            blueprint=pipe_llm_blueprint,
        )

        # Without | with_images filter, no images should be included
        assert pipe_llm.llm_prompt_spec.image_references is None

    def test_nested_image_with_filter_creates_nested_reference(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that struct with | with_images creates a NESTED reference."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test NESTED reference",
            inputs={"page": "Page"},
            output="Text",
            prompt="Describe: {{ page | with_images }}",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_nested_reference",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.image_references is not None
        assert len(pipe_llm.llm_prompt_spec.image_references) == 1
        ref = pipe_llm.llm_prompt_spec.image_references[0]
        assert ref.kind == ImageReferenceKind.NESTED
        assert ref.variable_path == "page"

    def test_nested_reference_has_correct_image_paths(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that NESTED reference includes correct nested_image_paths."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test nested paths",
            inputs={"page": "Page"},
            output="Text",
            prompt="{{ page | with_images }}",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_nested_paths",
            blueprint=pipe_llm_blueprint,
        )

        assert pipe_llm.llm_prompt_spec.image_references is not None
        ref = pipe_llm.llm_prompt_spec.image_references[0]
        assert ref.nested_image_paths is not None
        assert "text_and_images.images" in ref.nested_image_paths
        assert "page_view" in ref.nested_image_paths


# =============================================================================
# Prompt Token Substitution Tests
# =============================================================================


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPromptTextTokenSubstitution:
    """Tests for [Image N] token substitution in prompt text."""

    async def test_direct_image_replaced_with_token(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that direct Image input is replaced with [Image 1] token."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test token substitution",
            inputs={"image": "Image"},
            output="Text",
            prompt="Describe this image: @image",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_token_sub",
            blueprint=pipe_llm_blueprint,
        )

        image_url = ImageTestCases.IMAGE_FILE_PATH_PNG_1
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=ImageContent(url=image_url),
                name="image",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text

    async def test_direct_image_url_not_in_text(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that image URL does not appear in prompt text."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test URL not in text",
            inputs={"image": "Image"},
            output="Text",
            prompt="@image",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_no_url",
            blueprint=pipe_llm_blueprint,
        )

        image_url = ImageTestCases.IMAGE_FILE_PATH_PNG_1
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=ImageContent(url=image_url),
                name="image",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_text is not None
        assert image_url not in llm_prompt.user_text
        assert "ai_lympics" not in llm_prompt.user_text

    async def test_direct_list_items_replaced_with_tokens(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that Image[] items are replaced with [Image N] tokens."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test list tokens",
            inputs={"images": "Image[]"},
            output="Text",
            prompt="Analyze: $images",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_list_tokens",
            blueprint=pipe_llm_blueprint,
        )

        image_urls = [ImageTestCases.IMAGE_FILE_PATH_PNG_1, ImageTestCases.IMAGE_FILE_PATH_JPG_1]
        image_list = ListContent[ImageContent](items=[ImageContent(url=url) for url in image_urls])
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=image_list,
                name="images",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text
        assert "[Image 2]" in llm_prompt.user_text

    async def test_multiple_lists_numbered_globally(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that multiple Image[] inputs are numbered globally."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test multiple lists",
            inputs={"collection_a": "Image[]", "collection_b": "Image[]"},
            output="Text",
            prompt="First: $collection_a\nSecond: $collection_b",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_multiple_lists",
            blueprint=pipe_llm_blueprint,
        )

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

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text
        assert "[Image 2]" in llm_prompt.user_text
        assert "[Image 3]" in llm_prompt.user_text
        assert "[Image 4]" in llm_prompt.user_text

    async def test_no_filenames_in_prompt_text(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that no image filenames appear in prompt text."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test no filenames",
            inputs={"images": "Image[]"},
            output="Text",
            prompt="$images",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_no_filenames",
            blueprint=pipe_llm_blueprint,
        )

        image_list = ListContent[ImageContent](
            items=[
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_1),
            ]
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=image_list,
                name="images",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_text is not None
        assert "ai_lympics" not in llm_prompt.user_text
        assert "animal_lympics" not in llm_prompt.user_text
        assert ".png" not in llm_prompt.user_text
        assert ".jpg" not in llm_prompt.user_text


# =============================================================================
# Prompt Image Extraction Tests
# =============================================================================


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPromptImageExtraction:
    """Tests for image extraction into user_images list."""

    async def test_direct_image_in_user_images(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that direct Image is added to user_images."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test user_images",
            inputs={"image": "Image"},
            output="Text",
            prompt="@image",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_user_images",
            blueprint=pipe_llm_blueprint,
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
                name="image",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 1

    async def test_direct_list_all_in_user_images(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that all images from Image[] are in user_images."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test list user_images",
            inputs={"images": "Image[]"},
            output="Text",
            prompt="$images",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_list_user_images",
            blueprint=pipe_llm_blueprint,
        )

        image_list = ListContent[ImageContent](
            items=[
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_1),
                ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_2),
            ]
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=image_list,
                name="images",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 3

    async def test_nested_images_registered_via_filter(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that nested images with | with_images get registered to the ImageRegistry.

        Note: The current implementation registers images to the registry when the filter
        processes them, and the registry content is collected after template rendering.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test nested extraction",
            inputs={"page": "Page"},
            output="Text",
            prompt="{{ page | with_images }}",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_nested_extraction",
            blueprint=pipe_llm_blueprint,
        )

        page_content = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Some text"),
                images=[ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1)],
            ),
            page_view=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_1),
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.PAGE),
                content=page_content,
                name="page",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        # The prompt text should contain image tokens
        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text
        assert "[Image 2]" in llm_prompt.user_text

        # Images should be extracted to user_images
        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 2


# =============================================================================
# Inference Tests (with actual LLM calls or dry run)
# =============================================================================


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

        if pipe_run_mode != PipeRunMode.DRY:
            article = pipe_output.main_stuff_as(content_type=Article)
            assert article.title in {
                "2037 AI-Lympics Paris",
                "2037 AI-Lympics PARIS",
                "2037 AI-Lympics",
                "2037 AI-LYMPICS PARIS",
                "2037 AI-LYMPICS",
            }

    async def test_describe_page_with_nested_images(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test describing a page with nested images."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        image_content = ImageContent(url=f"file://{ImageTestCases.IMAGE_FILE_PATH_PNG_1}")
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

        if pipe_run_mode != PipeRunMode.DRY:
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

        if pipe_run_mode != PipeRunMode.DRY:
            assert pipe_output.main_stuff.concept.code == "Analysis"

    @pytest.mark.parametrize(("_topic", "data_url"), ImageTestCases.DATA_URL_TEST_CASES)
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
                pipe=get_required_pipe(pipe_code="extract_article_from_image"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=job_metadata,
            ),
        )

        assert pipe_output is not None
        assert pipe_output.main_stuff is not None
