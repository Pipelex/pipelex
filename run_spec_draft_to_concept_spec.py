import asyncio

from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline


async def run_spec_draft_to_concept_spec():
    """Run the pipeline and return the result."""
    return await execute_pipeline(
        pipe_code="spec_draft_to_concept_spec",
        input_memory={
            "concept_spec_draft": {
                "concept_code": "concept.ConceptSpecDraft",
                "content": {
                    "the_concept_code": "the_concept_code_value",
                    "description": "description_value",
                    "structure": "structure_value",
                    "refines": "refines_value",
                },
            },
            "concept_spec_structures": {
                "concept_code": "concept.ConceptStructureSpec",
                "content": {
                    "the_field_name": "the_field_name_value",
                    "description": "description_value",
                    "type": "text",
                    "required": False,
                    "default_value": "default_value_value  # TODO: Fill Any",
                },
            },
        },
    )


if __name__ == "__main__":
    # Initialize Pipelex
    Pipelex.make()

    # Run the pipeline
    result = asyncio.run(run_spec_draft_to_concept_spec())
