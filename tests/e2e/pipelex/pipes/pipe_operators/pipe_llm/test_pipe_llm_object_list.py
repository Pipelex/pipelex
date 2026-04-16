"""E2E test for PipeLLM with structured object list output."""

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexRunner


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.asyncio
class TestPipeLLMObjectList:
    async def test_craft_prompts(self, pipe_run_mode: PipeRunMode) -> None:
        """Test a PipeLLM pipe that generates a list of structured MoodboardPrompt objects."""
        pipeline_response = await PipelexRunner(
            library_dirs=["tests/e2e/pipelex/pipes/pipe_operators"], pipe_run_mode=pipe_run_mode
        ).execute_pipeline(
            pipe_code="craft_prompts",
            inputs={
                "inspiration": TextContent(text="1970s bohemian chic with earthy tones and flowing fabrics"),
            },
        )

        assert pipeline_response.pipe_output is not None
        assert pipeline_response.pipe_output.working_memory is not None
        assert pipeline_response.pipe_output.main_stuff is not None

        items = pipeline_response.pipe_output.main_stuff_as_list(item_type=TextContent)
        assert len(items) == 3

        pretty_print(items, title="Moodboard prompts")
