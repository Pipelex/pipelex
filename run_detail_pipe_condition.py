import asyncio

from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline


async def run_detail_pipe_condition():
    """Run the pipeline and return the result."""
    return await execute_pipeline(
        pipe_code="detail_pipe_condition",
        input_memory={
            "plan_draft": "plan_draft_text",
            "pipe_signature": {
                "concept_code": "pipe_design.PipeSignature",
                "content": {
                    "code": "code_value",
                    "type": "PipeFunc",
                    "pipe_category": "pipe_category_value  # TODO: Fill Literal",
                    "description": "description_value",
                    "inputs": {"inputs_key": "inputs_value"},
                    "result": "result_value",
                    "output": "output_value",
                    "pipe_dependencies": ["pipe_dependencies_item_1"],
                },
            },
            "concept_specs": {
                "concept_code": "concept.ConceptSpec",
                "content": {
                    "the_concept_code": "the_concept_code_value",
                    "description": "description_value",
                    "structure": {"structure_key": "structure_value"},
                    "refines": "refines_value",
                },
            },
        },
    )


if __name__ == "__main__":
    # Initialize Pipelex
    Pipelex.make()

    # Run the pipeline
    result = asyncio.run(run_detail_pipe_condition())
    print(result.main_stuff_as_str)
