"""Integration tests for image extraction into user_images list."""

from pathlib import Path
from typing import Callable

import pytest

from pipelex import pretty_print
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
from pipelex.hub import get_native_concept
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.tools.jinja2.jinja2_errors import Jinja2TemplateRenderError
from tests.cases import ImageTestCases


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
        pretty_print(llm_prompt.user_text, title="with_images filter - 2 images extracted")

    async def test_tag_then_with_images_raises_error(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that {{ pages | tag | with_images }} raises an error.

        The tag filter converts to string first, so with_images receives a string
        instead of structured data. This is detected and raises a clear error.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test tag then with_images raises error",
            inputs={"pages": "Page[]"},
            output="Text",
            prompt="{{ pages | tag | with_images }}",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_chained_filters",
            blueprint=pipe_llm_blueprint,
        )

        pages = ListContent[PageContent](
            items=[
                PageContent(
                    text_and_images=TextAndImagesContent(
                        text=TextContent(text="Page 1 text"),
                        images=[ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1)],
                    ),
                    page_view=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_1),
                ),
            ]
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.PAGE),
                content=pages,
                name="pages",
            ),
        )

        # Should raise error because tag converts to string before with_images
        with pytest.raises(Jinja2TemplateRenderError, match="does not implement the ImageRenderable protocol"):
            await pipe_llm.llm_prompt_spec.make_llm_prompt(
                output_concept_ref="Text",
                context_provider=working_memory,
            )

    async def test_tag_filter_renders_text(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that tag filter alone correctly wraps content in tags.

        This demonstrates the CORRECT way to use the tag filter for formatted output.
        Note: tag returns a string, so no images are extracted (use with_images for that).
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test tag filter alone",
            inputs={"pages": "Page[]"},
            output="Text",
            prompt="{{ pages | tag }}",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_tag_only",
            blueprint=pipe_llm_blueprint,
        )

        pages = ListContent[PageContent](
            items=[
                PageContent(
                    text_and_images=TextAndImagesContent(
                        text=TextContent(text="Page 1 text"),
                        images=[ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1)],
                    ),
                    page_view=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_1),
                ),
            ]
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.PAGE),
                content=pages,
                name="pages",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        # Tag filter produces formatted text output but NO image tokens or extraction
        assert llm_prompt.user_text is not None
        assert "```" in llm_prompt.user_text  # Tag wraps in code blocks by default
        assert "[Image 1]" not in llm_prompt.user_text  # No image tokens from tag
        assert llm_prompt.user_images is None or len(llm_prompt.user_images) == 0
        pretty_print(llm_prompt.user_text, title="tag filter prompt - formatted text, no images")

    async def test_with_images_then_tag_extracts_and_wraps(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that {{ pages | with_images | tag }} extracts images AND wraps in tags.

        This order works because:
        1. with_images extracts images and returns string with [Image N] tokens
        2. tag wraps that string in tags (```...``` or XML)

        The images are extracted because with_images processes structured data first.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test with_images then tag",
            inputs={"pages": "Page[]"},
            output="Text",
            prompt="{{ pages | with_images | tag }}",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_with_images_then_tag",
            blueprint=pipe_llm_blueprint,
        )

        pages = ListContent[PageContent](
            items=[
                PageContent(
                    text_and_images=TextAndImagesContent(
                        text=TextContent(text="Page 1 text"),
                        images=[ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1)],
                    ),
                    page_view=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_JPG_1),
                ),
            ]
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.PAGE),
                content=pages,
                name="pages",
            ),
        )

        llm_prompt = await pipe_llm.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        # with_images | tag: images ARE extracted AND content is wrapped in tags
        assert llm_prompt.user_text is not None
        assert "```" in llm_prompt.user_text  # Tag wraps in code blocks
        assert "[Image 1]" in llm_prompt.user_text  # Image tokens present
        assert "[Image 2]" in llm_prompt.user_text
        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 2
        pretty_print(llm_prompt.user_text, title="with_images | tag - images extracted AND wrapped in tags")
