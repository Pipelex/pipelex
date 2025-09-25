"""Test pipe sequence functionality with batching operations."""

from typing import cast

import pytest

from pipelex import log
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_input import TypedNamedInputRequirement
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_required_pipe
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipeline.job_metadata import JobMetadata
from tests.test_pipelines.pipe_controllers.pipe_sequence.pipe_sequence import Document, ProductRating


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio
async def test_review_analysis_sequence_with_batching(pipe_run_mode: PipeRunMode):
    """Test customer review analysis sequence with batching."""
    # Create test input - a document with reviews
    if pipe_run_mode == PipeRunMode.DRY:
        working_memory = WorkingMemoryFactory.make_for_dry_run(
            needed_inputs=[
                TypedNamedInputRequirement(
                    variable_name="document",
                    concept=ConceptFactory.make(
                        concept_code="Document",
                        domain="customer_feedback",
                        definition="Lorem ipsum",
                        structure_class_name="Document",
                    ),
                    structure_class=Document,
                ),
            ],
        )
        pipe = get_required_pipe(pipe_code="analyze_reviews_sequence")
        pipe_output = await pipe.run_pipe(
            job_metadata=JobMetadata(job_name="test_review_analysis_sequence_with_batching"),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
            working_memory=working_memory,
        )
    else:
        document_stuff = StuffFactory.make_stuff(
            name="document",
            concept=ConceptFactory.make(
                concept_code="Document",
                domain="customer_feedback",
                definition="customer_feedback.Document",
                structure_class_name="Document",
            ),
            content=Document(
                text="Review 1: Great product! Love the quality and fast shipping. 5 stars!\n\n\
                Review 2: Could be better. The product arrived damaged and customer service\
                      was slow to respond. 2 stars.\n\nReview 3: Excellent service! \
                        Quick delivery and exactly as described. Highly recommend! 5 stars!",
                title="Customer Reviews for Product XYZ",
            ),
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(document_stuff)
        # Execute the pipeline
        pipe_output = await execute_pipeline(
            pipe_code="analyze_reviews_sequence",
            working_memory=working_memory,
        )

    # Basic output validation
    assert pipe_output is not None
    assert pipe_output.working_memory is not None
    assert pipe_output.main_stuff is not None
    assert pipe_output.main_stuff.concept.code == "ProductRating"
    assert pipe_output.main_stuff.concept.domain == "customer_feedback"

    # Log the working memory for debugging
    log.debug("Final working memory after pipeline execution:")
    pipe_output.working_memory.pretty_print_summary()

    # Verify final product rating
    stuff = pipe_output.working_memory.get_stuff("product_rating")
    # Use cast to tell the type system what we know about the object
    product_rating_stuff = cast("ProductRating", stuff.content)
    assert product_rating_stuff is not None

    # Check that the ProductRating has meaningful values
    assert isinstance(product_rating_stuff.overall_rating, float), f"Rating should be a float, got {type(product_rating_stuff.overall_rating)}"
    assert isinstance(product_rating_stuff.total_reviews, int), f"Total reviews should be an int, got {type(product_rating_stuff.total_reviews)}"
    assert len(product_rating_stuff.explanation) > 0, "Should have an explanation for the rating"
