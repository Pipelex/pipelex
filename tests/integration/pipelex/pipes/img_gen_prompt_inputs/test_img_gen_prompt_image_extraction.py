"""Integration tests for image extraction into img_gen prompt input_images list."""

from pathlib import Path
from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from tests.cases import ImageTestCases


@pytest.mark.asyncio(loop_scope="class")
class TestImgGenPromptImageExtraction:
    """Tests for image extraction into input_images list in img_gen prompts."""

    async def test_dotted_path_bare_jinja2_produces_placeholder(
        self,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test that bare {{ page.page_view }} syntax produces [Image N] for registered images.

        When a dotted path references a nested image field on a structured content
        like PageContent, the Jinja2 finalize callback should intercept the
        ImageContent before str() conversion and replace it with [Image N].
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        blueprint = PipeImgGenBlueprint(
            description="Test dotted path image in img_gen prompt",
            inputs={"page.page_view": "Image", "page": "Page"},
            output="Image",
            prompt="Edit this image: {{ page.page_view }}",
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_dotted_path_img_gen",
            blueprint=blueprint,
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

        img_gen_prompt = await pipe.img_gen_prompt_blueprint.make_img_gen_prompt(
            context_provider=working_memory,
        )

        # The nested image should be extracted to input_images
        assert img_gen_prompt.input_images is not None
        assert len(img_gen_prompt.input_images) == 1

        # The prompt text should contain [Image 1] placeholder, NOT the raw URL
        assert "[Image 1]" in img_gen_prompt.positive_text, f"Expected '[Image 1]' in prompt, got: {img_gen_prompt.positive_text}"
        assert ImageTestCases.IMAGE_FILE_PATH_PNG_1 not in img_gen_prompt.positive_text, (
            f"URL should not appear in prompt text: {img_gen_prompt.positive_text}"
        )
        pretty_print(img_gen_prompt.positive_text, title="Dotted path bare Jinja2 in img_gen prompt")

    async def test_dotted_path_dollar_syntax_produces_placeholder(
        self,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test that $page.page_view syntax produces [Image N] for registered images.

        The $ syntax becomes {{ page.page_view|format() }}. The format filter should
        detect the registered image and return the placeholder instead of calling
        rendered_plain() which would produce the URL.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        blueprint = PipeImgGenBlueprint(
            description="Test dollar dotted path image in img_gen prompt",
            inputs={"page.page_view": "Image", "page": "Page"},
            output="Image",
            prompt="Edit this image: $page.page_view",
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_dollar_dotted_path_img_gen",
            blueprint=blueprint,
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

        img_gen_prompt = await pipe.img_gen_prompt_blueprint.make_img_gen_prompt(
            context_provider=working_memory,
        )

        # The nested image should be extracted to input_images
        assert img_gen_prompt.input_images is not None
        assert len(img_gen_prompt.input_images) == 1

        # The prompt text should contain [Image 1] placeholder, NOT the raw URL
        assert "[Image 1]" in img_gen_prompt.positive_text, f"Expected '[Image 1]' in prompt, got: {img_gen_prompt.positive_text}"
        assert ImageTestCases.IMAGE_FILE_PATH_PNG_1 not in img_gen_prompt.positive_text, (
            f"URL should not appear in prompt text: {img_gen_prompt.positive_text}"
        )
        pretty_print(img_gen_prompt.positive_text, title="Dollar dotted path in img_gen prompt")

    async def test_dotted_path_at_syntax_produces_placeholder(
        self,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        """Test that @page.page_view syntax produces [Image N] for registered images.

        The @ syntax becomes {{ page.page_view|tag("page.page_view") }}. The tag filter
        already checks the image registry and returns the placeholder.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        blueprint = PipeImgGenBlueprint(
            description="Test at dotted path image in img_gen prompt",
            inputs={"page.page_view": "Image", "page": "Page"},
            output="Image",
            prompt="Edit this image: @page.page_view",
        )

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="test_pipes",
            pipe_code="test_at_dotted_path_img_gen",
            blueprint=blueprint,
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

        img_gen_prompt = await pipe.img_gen_prompt_blueprint.make_img_gen_prompt(
            context_provider=working_memory,
        )

        # The nested image should be extracted to input_images
        assert img_gen_prompt.input_images is not None
        assert len(img_gen_prompt.input_images) == 1

        # The prompt text should contain [Image 1] placeholder, NOT the raw URL
        assert "[Image 1]" in img_gen_prompt.positive_text, f"Expected '[Image 1]' in prompt, got: {img_gen_prompt.positive_text}"
        assert ImageTestCases.IMAGE_FILE_PATH_PNG_1 not in img_gen_prompt.positive_text, (
            f"URL should not appear in prompt text: {img_gen_prompt.positive_text}"
        )
        pretty_print(img_gen_prompt.positive_text, title="At dotted path in img_gen prompt")
