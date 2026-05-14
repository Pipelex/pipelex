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
from pipelex.pipe_operators.llm.template_image_analyzer import WithImagesFilterError
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

    async def test_direct_nested_image_via_dotted_path(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that direct nested image reference via dotted path produces [Image N] token.

        This tests the case where:
        - inputs declares a dotted path to an image field: {"page.page_view": "Image"}
        - prompt uses @page.page_view which becomes {{ page.page_view|tag("page.page_view") }}
        - The tag filter should detect the registered image and return [Image N]

        This verifies that the tag filter correctly substitutes registered images,
        which is essential for nested image fields on structured content like PageContent.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test direct nested image reference",
            inputs={"page.page_view": "Image", "page": "Page"},
            output="Text",
            prompt="Describe this image: $page.page_view",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_direct_nested_image",
            blueprint=pipe_llm_blueprint,
        )

        page_content = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Some text content"),
                images=[],
            ),
            page_view=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
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

        # The nested image should be extracted to user_images
        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 1

        # The prompt text should contain [Image 1] placeholder, NOT the raw ImageContent
        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text
        # Verify it doesn't contain the URL directly (would indicate failed substitution)
        assert ImageTestCases.IMAGE_FILE_PATH_PNG_1 not in llm_prompt.user_text
        pretty_print(llm_prompt.user_text, title="Direct nested image via dotted path")

    async def test_dollar_syntax_for_direct_image_produces_placeholder(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that $image syntax (format filter) produces [Image N] for registered images.

        The $image syntax becomes {{ image|format() }}. For direct images that are
        registered via user_image_references, this should produce [Image N] tokens
        in the prompt text, NOT the raw URL.

        This test verifies that the format filter properly integrates with the ImageRegistry
        to substitute registered images with their placeholders.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test $image syntax produces placeholder",
            inputs={"image": "Image"},
            output="Text",
            prompt="Describe this: $image",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_dollar_image_syntax",
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

        # Image should be extracted
        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 1

        # The prompt text should contain [Image 1], NOT the URL
        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text, f"Expected '[Image 1]' in prompt, got: {llm_prompt.user_text}"
        assert ImageTestCases.IMAGE_FILE_PATH_PNG_1 not in llm_prompt.user_text, f"URL should not appear in prompt text: {llm_prompt.user_text}"
        pretty_print(llm_prompt.user_text, title="$image syntax - should show [Image 1]")

    async def test_plain_jinja2_image_produces_placeholder(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that plain {{ image }} syntax produces [Image N] for registered images.

        When rendering a direct image without any filter (plain {{ image }}),
        the image should still be substituted with [Image N] since it's registered
        via user_image_references.

        This test verifies that the default string conversion of StuffArtefact
        properly integrates with the ImageRegistry.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test plain {{ image }} produces placeholder",
            inputs={"image": "Image"},
            output="Text",
            prompt="Describe this: {{ image }}",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_plain_jinja2_image",
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

        # Image should be extracted
        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 1

        # The prompt text should contain [Image 1], NOT StuffArtefact(image) or the URL
        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text, f"Expected '[Image 1]' in prompt, got: {llm_prompt.user_text}"
        assert "StuffArtefact" not in llm_prompt.user_text, f"StuffArtefact should not appear in prompt text: {llm_prompt.user_text}"
        assert ImageTestCases.IMAGE_FILE_PATH_PNG_1 not in llm_prompt.user_text, f"URL should not appear in prompt text: {llm_prompt.user_text}"
        pretty_print(llm_prompt.user_text, title="plain {{ image }} - should show [Image 1]")

    async def test_at_and_dollar_syntax_render_same_content(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that @image and $image render the same content (except for tags).

        Both syntaxes should produce [Image 1] as the content.
        The only difference should be that @ wraps in tags, $ does not.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        # Test @image
        pipe_at = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_at_image",
            blueprint=PipeLLMBlueprint(
                description="Test @image",
                inputs={"image": "Image"},
                output="Text",
                prompt="Content:\n@image",
            ),
        )

        # Test $image
        pipe_dollar = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_dollar_image",
            blueprint=PipeLLMBlueprint(
                description="Test $image",
                inputs={"image": "Image"},
                output="Text",
                prompt="Content: $image",
            ),
        )

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.IMAGE),
                content=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
                name="image",
            ),
        )

        prompt_at = await pipe_at.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )
        prompt_dollar = await pipe_dollar.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        pretty_print(prompt_at.user_text, title="@image syntax output")
        pretty_print(prompt_dollar.user_text, title="$image syntax output")

        # Both should have the same images extracted
        assert prompt_at.user_images is not None
        assert prompt_dollar.user_images is not None
        assert len(prompt_at.user_images) == len(prompt_dollar.user_images) == 1

        # $image should produce [Image 1] inline
        assert prompt_dollar.user_text is not None
        assert "[Image 1]" in prompt_dollar.user_text

        # @image should produce [Image 1] (possibly wrapped in tags)
        assert prompt_at.user_text is not None
        assert "[Image 1]" in prompt_at.user_text

    async def test_at_and_dollar_syntax_for_image_list(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that @images and $images render lists of images correctly.

        Both syntaxes should produce [Image 1], [Image 2], [Image 3] as content.
        The only difference should be that @ wraps in tags, $ does not.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        # Test @images (list)
        pipe_at = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_at_images_list",
            blueprint=PipeLLMBlueprint(
                description="Test @images list",
                inputs={"images": "Image[]"},
                output="Text",
                prompt="Here are the images:\n@images",
            ),
        )

        # Test $images (list)
        pipe_dollar = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_dollar_images_list",
            blueprint=PipeLLMBlueprint(
                description="Test $images list",
                inputs={"images": "Image[]"},
                output="Text",
                prompt="Here are the images: $images",
            ),
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

        prompt_at = await pipe_at.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )
        prompt_dollar = await pipe_dollar.llm_prompt_spec.make_llm_prompt(
            output_concept_ref="Text",
            context_provider=working_memory,
        )

        pretty_print(prompt_at.user_text, title="@images (list) syntax output")
        pretty_print(prompt_dollar.user_text, title="$images (list) syntax output")

        # Both should have the same images extracted
        assert prompt_at.user_images is not None
        assert prompt_dollar.user_images is not None
        assert len(prompt_at.user_images) == len(prompt_dollar.user_images) == 3

        # $images should produce [Image 1], [Image 2], [Image 3] inline
        assert prompt_dollar.user_text is not None
        assert "[Image 1]" in prompt_dollar.user_text
        assert "[Image 2]" in prompt_dollar.user_text
        assert "[Image 3]" in prompt_dollar.user_text

        # @images should produce the same content wrapped in tags
        assert prompt_at.user_text is not None
        assert "[Image 1]" in prompt_at.user_text
        assert "[Image 2]" in prompt_at.user_text
        assert "[Image 3]" in prompt_at.user_text

    async def test_with_images_filter_on_single_image_raises_error(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that {{ image | with_images }} raises an error for direct images.

        The with_images filter is designed for types with nested images (like PageContent).
        For direct Image inputs, use $image or @image syntax instead.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test with_images on single image",
            inputs={"image": "Image"},
            output="Text",
            prompt="Describe this: {{ image | with_images }}",
        )

        # Should raise error because with_images is for nested images, not direct Image inputs
        with pytest.raises(WithImagesFilterError, match="has no nested images"):
            PipeFactory[PipeLLM].make_from_blueprint(
                domain_code="test_pipes",
                pipe_code="test_with_images_single",
                blueprint=pipe_llm_blueprint,
            )

    async def test_dotted_path_bare_jinja2_produces_placeholder(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that bare {{ page.page_view }} syntax produces [Image N] for registered images.

        When a dotted path references a nested image field on a structured content
        like PageContent, the Jinja2 finalize callback should intercept the
        ImageContent before str() conversion and replace it with [Image N].
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test bare Jinja2 dotted path image",
            inputs={"page.page_view": "Image", "page": "Page"},
            output="Text",
            prompt="Describe this image: {{ page.page_view }}",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_bare_jinja2_dotted_image",
            blueprint=pipe_llm_blueprint,
        )

        page_content = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Some text content"),
                images=[],
            ),
            page_view=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
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

        # The nested image should be extracted to user_images
        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 1

        # The prompt text should contain [Image 1] placeholder, NOT the raw URL
        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text, f"Expected '[Image 1]' in prompt, got: {llm_prompt.user_text}"
        assert ImageTestCases.IMAGE_FILE_PATH_PNG_1 not in llm_prompt.user_text, f"URL should not appear in prompt text: {llm_prompt.user_text}"
        pretty_print(llm_prompt.user_text, title="Bare {{ page.page_view }} - should show [Image 1]")

    async def test_dotted_path_dollar_syntax_produces_placeholder(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that $page.page_view syntax produces [Image N] for registered images.

        The $ syntax becomes {{ page.page_view|format() }}. The format filter should
        detect the registered image via the ImageRegistry and return the placeholder
        instead of calling rendered_plain() which would produce the URL.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        pipe_llm_blueprint = PipeLLMBlueprint(
            description="Test dollar dotted path image",
            inputs={"page.page_view": "Image", "page": "Page"},
            output="Text",
            prompt="Describe this image: $page.page_view",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_dollar_dotted_image",
            blueprint=pipe_llm_blueprint,
        )

        page_content = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Some text content"),
                images=[],
            ),
            page_view=ImageContent(url=ImageTestCases.IMAGE_FILE_PATH_PNG_1),
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

        # The nested image should be extracted to user_images
        assert llm_prompt.user_images is not None
        assert len(llm_prompt.user_images) == 1

        # The prompt text should contain [Image 1] placeholder, NOT the raw URL
        assert llm_prompt.user_text is not None
        assert "[Image 1]" in llm_prompt.user_text, f"Expected '[Image 1]' in prompt, got: {llm_prompt.user_text}"
        assert ImageTestCases.IMAGE_FILE_PATH_PNG_1 not in llm_prompt.user_text, f"URL should not appear in prompt text: {llm_prompt.user_text}"
        pretty_print(llm_prompt.user_text, title="$page.page_view - should show [Image 1]")
