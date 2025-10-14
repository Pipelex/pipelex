import asyncio

from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline


async def run_pipe_builder():
    """Run the pipeline and return the result."""
    return await execute_pipeline(
        pipe_code="pipe_builder",
        input_memory={
            "brief": "brief_text",
        },
    )


if __name__ == "__main__":
    # Initialize Pipelex
    Pipelex.make()

    # Run the pipeline
    result = asyncio.run(run_pipe_builder())
    print(result.main_stuff_as_str)
