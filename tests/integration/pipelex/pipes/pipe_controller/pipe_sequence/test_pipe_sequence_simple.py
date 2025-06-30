"""Test simple pipe sequence functionality without batching."""

import pytest

from pipelex.core.stuff_content import TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.pipeline.execute import execute_pipeline


@pytest.mark.dry_runnable
@pytest.mark.asyncio
async def test_simple_text_sequence():
    """Test simple text processing sequence without batching."""
    # Create test input
    raw_text_stuff = StuffFactory.make_stuff(
        name="raw_text",
        concept_str="simple_text_processing.RawText",
        content=TextContent(text="This is  some   messy    text with bad spacing."),
    )

    working_memory = WorkingMemoryFactory.make_from_multiple_stuffs([raw_text_stuff])

    # Execute the pipeline
    pipe_output = await execute_pipeline(
        pipe_code="simple_text_sequence",
        working_memory=working_memory,
    )

    # Basic assertions
    assert pipe_output is not None
    assert pipe_output.working_memory is not None
    assert pipe_output.main_stuff is not None
    assert pipe_output.main_stuff.concept_code == "simple_text_processing.SummaryText"
