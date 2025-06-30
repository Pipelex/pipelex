"""Test pipe sequence functionality with batching operations."""

import pytest

from pipelex.core.stuff_content import TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.pipeline.execute import execute_pipeline


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio
async def test_review_analysis_sequence_with_batching():
    """Test customer review analysis sequence with batching."""
    # Create test input - a document with reviews
    document_stuff = StuffFactory.make_stuff(
        name="document",
        concept_str="customer_feedback.Document",
        content=TextContent(text="Review 1: Great product! Review 2: Could be better. Review 3: Excellent service!"),
    )

    working_memory = WorkingMemoryFactory.make_from_multiple_stuffs([document_stuff])

    # Execute the pipeline
    pipe_output = await execute_pipeline(
        pipe_code="analyze_reviews_sequence",
        working_memory=working_memory,
    )
    assert pipe_output is not None
    assert pipe_output.working_memory is not None
    assert pipe_output.main_stuff is not None
    assert pipe_output.main_stuff.concept_code == "customer_feedback.ProductRating"
