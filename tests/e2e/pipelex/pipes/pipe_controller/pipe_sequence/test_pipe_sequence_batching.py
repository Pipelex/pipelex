"""Test pipe sequence functionality with batching operations."""

from pathlib import Path
from typing import Callable, cast

import pytest

from pipelex import log
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.inputs.input_stuff_specs import TypedNamedStuffSpec
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.method_hub import get_required_pipe
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.controller.pipe_sequence.pipe_sequence import Document, ProductRating


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio
async def test_review_analysis_sequence_with_batching(
    job_metadata: JobMetadata, pipe_run_mode: PipeRunMode, load_test_library: Callable[[list[Path]], None]
):
    load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_sequence")])
    """Test customer review analysis sequence with batching."""
    # Create test input - a document with reviews
    if pipe_run_mode.is_dry:
        working_memory = WorkingMemoryFactory.make_mock_inputs(
            needed_inputs=[
                TypedNamedStuffSpec(
                    variable_name="document",
                    concept=ConceptFactory.make(
                        concept_code="Document",
                        domain_code="customer_feedback",
                        description="Lorem ipsum",
                        structure_class_name="Document",
                    ),
                    structure_class=Document,
                ),
            ],
        )
        pipe = get_required_pipe(pipe_code="analyze_reviews_sequence")
        pipe_output = await pipe.run_pipe(
            job_metadata=job_metadata,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            working_memory=working_memory,
        )
    else:
        document_stuff = StuffFactory.make_stuff(
            name="document",
            concept=ConceptFactory.make(
                concept_code="Document",
                domain_code="customer_feedback",
                description="customer_feedback.Document",
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
        runner = PipelexMTHDSProtocol()
        response = await runner.execute(
            pipe_code="analyze_reviews_sequence",
            inputs=working_memory,
        )
        pipe_output = response.pipe_output

    # Basic output validation
    assert pipe_output is not None
    assert pipe_output.working_memory is not None
    assert pipe_output.main_stuff is not None
    assert pipe_output.main_stuff.concept.code == "ProductRating"
    assert pipe_output.main_stuff.concept.domain_code == "customer_feedback"

    # Log the working memory for debugging
    log.verbose("Final working memory after pipeline execution:")
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
