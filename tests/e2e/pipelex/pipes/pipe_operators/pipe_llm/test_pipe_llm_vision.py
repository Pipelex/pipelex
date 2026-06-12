"""E2E test for PipeLLM with vision capabilities."""

import pytest

from pipelex import pretty_print, pretty_print_md
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from tests.e2e.pipelex.pipes.pipe_operators.pipe_llm.pipe_llm_vision import VisionAnalysisE2E
from tests.integration.pipelex.cogt.test_data import LLMVisionTestCases
from tests.integration.pipelex.test_data import PipeTestCases


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio
class TestPipeLLMVision:
    async def test_describe_image_single(self, pipe_run_mode: PipeRunMode):
        # Execute the pipeline with an image
        pipeline_response = await PipelexMTHDSProtocol(library_dirs=["tests/e2e/pipelex/pipes/pipe_operators"], pipe_run_mode=pipe_run_mode).execute(
            pipe_code="describe_image_e2e",
            inputs={
                "image": ImageContent(url=LLMVisionTestCases.URL_CLOUDFRONT_ALAN_TURING_JPG),
            },
        )

        # Basic assertions
        assert pipeline_response.pipe_output is not None
        assert pipeline_response.pipe_output.working_memory is not None
        assert pipeline_response.pipe_output.main_stuff is not None

        # Get the result as text
        result_text = pipeline_response.pipe_output.main_stuff_as_str
        assert result_text is not None
        assert len(result_text) > 0

        # Log output
        pretty_print(result_text, title="Image Description")

        # Verify the description is reasonable
        assert len(result_text.strip()) > 20

    @pytest.mark.parametrize(
        "pipe_code",
        [
            "describe_image_number_1_only_e2e",
            "describe_image_number_2_only_e2e",
        ],
    )
    async def test_describe_images_multiple(self, pipe_run_mode: PipeRunMode, pipe_code: str):
        """Test the describe_image pipeline with multiple images to discriminate."""
        # Execute the pipeline with an image
        pipeline_response = await PipelexMTHDSProtocol(library_dirs=["tests/e2e/pipelex/pipes/pipe_operators"], pipe_run_mode=pipe_run_mode).execute(
            pipe_code=pipe_code,
            inputs={
                "image_a": ImageContent(url=LLMVisionTestCases.URL_CLOUDFRONT_ALAN_TURING_JPG),
                "image_b": ImageContent(url=PipeTestCases.URL_IMG_FASHION_PHOTO_1),
            },
        )

        description = pipeline_response.pipe_output.main_stuff_as_str
        pretty_print_md(description, title=f"Image Description ({pipe_code})")

    async def test_structured_analysis_of_image_with_gantt_chart(self, pipe_run_mode: PipeRunMode):
        """Test vision with a more complex image (Gantt chart)."""
        # Execute the pipeline with a complex image
        pipeline_response = await PipelexMTHDSProtocol(library_dirs=["tests/e2e/pipelex/pipes/pipe_operators"], pipe_run_mode=pipe_run_mode).execute(
            pipe_code="vision_analysis_e2e",
            inputs={
                "image": ImageContent(url=PipeTestCases.URL_IMG_GANTT_PNG),
            },
        )

        # Get the result as text
        result = pipeline_response.pipe_output.main_stuff_as(content_type=VisionAnalysisE2E)

        # Log output
        pretty_print(result, title="Gantt Chart Description")
