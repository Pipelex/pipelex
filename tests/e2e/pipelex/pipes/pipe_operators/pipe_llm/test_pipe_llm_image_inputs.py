"""E2E tests for image inputs in PipeLLM using execute_pipeline()."""

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexRunner
from tests.cases import ImageTestCases
from tests.e2e.pipelex.pipes.pipe_operators.pipe_llm.pipe_llm_image_inputs import (
    ImageDescriptionE2E,
    ImageListAnalysisE2E,
    PageDescriptionE2E,
)
from tests.integration.pipelex.cogt.test_data import LLMVisionTestCases

LIBRARY_DIRS = ["tests/e2e/pipelex/pipes/pipe_operators"]


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio
class TestImageInputsE2E:
    """E2E tests for image input handling using execute_pipeline()."""

    async def test_direct_single_image(self, pipe_run_mode: PipeRunMode) -> None:
        """Test single direct image input."""
        runner = PipelexRunner(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute_pipeline(
            pipe_code="describe_single_image_e2e",
            inputs={
                "image": ImageContent(url=LLMVisionTestCases.URL_CLOUDFRONT_ALAN_TURING_JPG),
            },
        )
        pipe_output = response.pipe_output

        assert pipe_output.main_stuff is not None
        if pipe_run_mode.is_live:
            result = pipe_output.main_stuff_as(content_type=ImageDescriptionE2E)
            pretty_print(result, title="Direct Image Description")
            assert len(result.description) > 10

    async def test_image_list_input(self, pipe_run_mode: PipeRunMode) -> None:
        """Test image list input counts images correctly."""
        images = ListContent[ImageContent](
            items=[
                ImageContent(url=LLMVisionTestCases.URL_CLOUDFRONT_ALAN_TURING_JPG),
                ImageContent(url=ImageTestCases.LOGO_TINY_PNG_DATA_URL),
            ]
        )

        runner = PipelexRunner(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute_pipeline(
            pipe_code="analyze_image_list_e2e",
            inputs={"images": images},
        )
        pipe_output = response.pipe_output

        assert pipe_output.main_stuff is not None
        if pipe_run_mode.is_live:
            analysis = pipe_output.main_stuff_as(content_type=ImageListAnalysisE2E)
            pretty_print(analysis, title="Image List Analysis")
            assert analysis.image_count == 2

    async def test_compare_image_lists(self, pipe_run_mode: PipeRunMode) -> None:
        """Test comparing two image collections."""
        collection_a = ListContent[ImageContent](items=[ImageContent(url=LLMVisionTestCases.URL_CLOUDFRONT_ALAN_TURING_JPG)])
        collection_b = ListContent[ImageContent](items=[ImageContent(url=ImageTestCases.LOGO_TINY_PNG_DATA_URL)])

        runner = PipelexRunner(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute_pipeline(
            pipe_code="compare_image_lists_e2e",
            inputs={
                "collection_a": collection_a,
                "collection_b": collection_b,
            },
        )
        pipe_output = response.pipe_output

        assert pipe_output.main_stuff is not None
        if pipe_run_mode.is_live:
            analysis = pipe_output.main_stuff_as(content_type=ImageListAnalysisE2E)
            pretty_print(analysis, title="Image Lists Comparison")

    async def test_page_with_images_filter_extracts_images(self, pipe_run_mode: PipeRunMode) -> None:
        """Test that | with_images filter extracts nested images.

        CRITICAL TEST: Verifies the bug fix for StuffArtefact handling.
        """
        page_content = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Page text about AI Olympics"),
                images=[ImageContent(url=LLMVisionTestCases.URL_CLOUDFRONT_ALAN_TURING_JPG)],
            ),
            page_view=ImageContent(url=ImageTestCases.LOGO_TINY_PNG_DATA_URL),
        )

        runner = PipelexRunner(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute_pipeline(
            pipe_code="describe_page_with_images_e2e",
            inputs={"page": page_content},
        )
        pipe_output = response.pipe_output

        assert pipe_output.main_stuff is not None
        if pipe_run_mode.is_live:
            result = pipe_output.main_stuff_as(content_type=PageDescriptionE2E)
            pretty_print(result, title="Page With Images Filter")
            assert result.can_see_image_content is True

    async def test_page_without_filter_no_images_sent(self, pipe_run_mode: PipeRunMode) -> None:
        """Test that page WITHOUT | with_images does NOT send images.

        CRITICAL TEST: Verifies images are only sent when explicitly requested.
        """
        page_content = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="This text describes the Eiffel Tower"),
                images=[ImageContent(url=LLMVisionTestCases.URL_CLOUDFRONT_ALAN_TURING_JPG)],
            ),
            page_view=ImageContent(url=ImageTestCases.LOGO_TINY_PNG_DATA_URL),
        )

        runner = PipelexRunner(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute_pipeline(
            pipe_code="describe_page_text_only_e2e",
            inputs={"page": page_content},
        )
        pipe_output = response.pipe_output

        assert pipe_output.main_stuff is not None
        if pipe_run_mode.is_live:
            result = pipe_output.main_stuff_as(content_type=PageDescriptionE2E)
            pretty_print(result, title="Page Without Images Filter")
            # Without the filter, LLM should not see images
            assert result.can_see_image_content is False

    async def test_mixed_direct_and_nested_images(self, pipe_run_mode: PipeRunMode) -> None:
        """Test combining direct image with nested images from page."""
        page_content = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Page content"),
                images=[],
            ),
            page_view=ImageContent(url=ImageTestCases.LOGO_TINY_PNG_DATA_URL),
        )

        runner = PipelexRunner(
            library_dirs=LIBRARY_DIRS,
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute_pipeline(
            pipe_code="mixed_image_inputs_e2e",
            inputs={
                "direct_image": ImageContent(url=LLMVisionTestCases.URL_CLOUDFRONT_ALAN_TURING_JPG),
                "page": page_content,
            },
        )
        pipe_output = response.pipe_output

        assert pipe_output.main_stuff is not None
        if pipe_run_mode.is_live:
            result = pipe_output.main_stuff_as(content_type=PageDescriptionE2E)
            pretty_print(result, title="Mixed Image Inputs")
            # Should have seen images (direct + nested from page_view)
            assert result.can_see_image_content is True
