"""E2E test for PipeLLM with vision capabilities."""

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.pipeline.execute import execute_pipeline
from tests.integration.pipelex.cogt.test_data import LLMVisionTestCases


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio
class TestPipeLLMVision:
    """Test PipeLLM with vision capabilities."""

    async def test_describe_image(self):
        """Test the describe_image pipeline with a simple image."""
        # Execute the pipeline with an image
        pipe_output = await execute_pipeline(
            pipe_code="describe_image",
            inputs={
                "image": ImageContent(url=LLMVisionTestCases.PATH_IMG_GANTT_1),
            },
        )

        # Get the result as text
        result_text = pipe_output.main_stuff_as_str

        # Basic assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None
        assert result_text is not None
        assert len(result_text) > 0

        # Log output
        pretty_print(result_text, title="Image Description")

        # Verify the description is reasonable
        assert len(result_text.strip()) > 20

    @pytest.mark.parametrize(
        "pipe_code",
        [
            "describe_image_number_1_only",
            "describe_image_number_2_only",
        ],
    )
    async def test_describe_images_discriminate(self, pipe_code: str):
        """Test the describe_image pipeline with multiple images to discriminate."""
        # Execute the pipeline with an image
        pipe_output = await execute_pipeline(
            pipe_code=pipe_code,
            inputs={
                "imageA": ImageContent(url=LLMVisionTestCases.PATH_IMG_GANTT_1),
                "imageB": ImageContent(url=LLMVisionTestCases.PATH_IMG_JPEG_3),
            },
        )

        result = pipe_output.main_stuff
        pretty_print(result, title=f"Image Description ({pipe_code})")

    async def test_structured_analysis_of_image_with_gantt_chart(self):
        """Test vision with a more complex image (Gantt chart)."""
        # Execute the pipeline with a complex image
        pipe_output = await execute_pipeline(
            pipe_code="vision_analysis",
            inputs={
                "image": ImageContent(url=LLMVisionTestCases.PATH_IMG_GANTT_1),
            },
        )

        # Get the result as text
        # result = pipe_output.main_stuff_as(content_type=VisionAnalysis)
        result = pipe_output.main_stuff

        # Log output
        pretty_print(result, title="Gantt Chart Description")
