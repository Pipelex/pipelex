"""Test pipe sequence functionality with batching operations."""

import pytest

from pipelex import log
from pipelex.core.pipe_run_params import PipeRunMode
from pipelex.core.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import get_required_pipe
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipeline.job_metadata import JobMetadata
from tests.pipelines.pipe_controllers.pipe_sequence.pipe_sequence import Document, ProductRating


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio
async def test_review_analysis_sequence_with_batching(pipe_run_mode: PipeRunMode):
    """Test customer review analysis sequence with batching."""
    # Create test input - a document with reviews
    document_stuff = StuffFactory.make_stuff(
        name="document",
        concept_str="customer_feedback.Document",
        content=Document(
            text="Review 1: Great product! Love the quality and fast shipping. 5 stars!\n\n\
                Review 2: Could be better. The product arrived damaged and customer service\
                      was slow to respond. 2 stars.\n\nReview 3: Excellent service! \
                        Quick delivery and exactly as described. Highly recommend! 5 stars!",
            title="Customer Reviews for Product XYZ",
        ),
    )
    working_memory = WorkingMemoryFactory.make_from_single_stuff(document_stuff)
    if pipe_run_mode == PipeRunMode.DRY:
        pipe = get_required_pipe(pipe_code="analyze_reviews_sequence")
        pipe_output = await pipe.dry_run_pipe(
            job_metadata=JobMetadata(job_name="test_review_analysis_sequence_with_batching"),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
            working_memory=working_memory,
        )

    # Execute the pipeline
    pipe_output = await execute_pipeline(
        pipe_code="analyze_reviews_sequence",
        working_memory=working_memory,
    )

    # Basic output validation
    assert pipe_output is not None
    assert pipe_output.working_memory is not None
    assert pipe_output.main_stuff is not None
    assert pipe_output.main_stuff.concept_code == "customer_feedback.ProductRating"

    # Log the working memory for debugging
    log.info("Final working memory after pipeline execution:")
    pipe_output.working_memory.pretty_print_summary()

    # Verify final product rating
    product_rating_stuff = pipe_output.working_memory.get_stuff("product_rating")
    assert product_rating_stuff is not None
    assert isinstance(product_rating_stuff.content, ProductRating)

    # Check that the ProductRating has meaningful values
    rating_content = product_rating_stuff.content
    assert 1.0 <= rating_content.overall_rating <= 5.0, f"Rating should be between 1-5, got {rating_content.overall_rating}"
    assert rating_content.total_reviews > 0, "Should have analyzed at least one review"
    assert len(rating_content.explanation) > 0, "Should have an explanation for the rating"

    log.info(f"Final product rating: {rating_content.overall_rating}/5 based on {rating_content.total_reviews} reviews")
    log.info(f"Rating explanation: {rating_content.explanation}")

    # Verify the batching worked - we should have processed multiple reviews
    total_sentiment_reviews = rating_content.positive_count + rating_content.negative_count + rating_content.neutral_count
    if total_sentiment_reviews > 0:
        log.info(
            f"Sentiment breakdown: {rating_content.positive_count} positive, \
                {rating_content.negative_count} negative, {rating_content.neutral_count} neutral"
        )
        assert total_sentiment_reviews == rating_content.total_reviews, "Sentiment counts should match total reviews"
