from typing import Literal, Optional

from pydantic import Field

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeBatchBlueprint(PipeBlueprint):
    """
    PipeBatch is used to run a pipe on a list of items in parallel.
    This is a pipe Controller, it orchestrates the execution of a pipe on a list of items.

    This pipe is mostly used directly inside a `PipeSequence` pipe like so:
    ```toml
    [pipe.sequence_with_batch]
    type = "Sequence"
    description = "A Sequence of pipes"
    inputs = { input_data = "ConceptName" }
    output = "OutputConceptName"
    steps = [
        { pipe = "pipe_to_apply", batch_over = "input_list", batch_as = "current_item", result = "batch_results" }
    ]
    ```
    ## Key Parameters
    - `pipe`: The pipe operation to apply to each element in the batch
    - `batch_over`: The name of the list in the context to iterate over
    - `batch_as`: The name to use for the current element in the pipe's context
    - `result`: Where to store the results of the batch operation
    """

    type: Literal["PipeBatch"] = "PipeBatch"
    branch_pipe_code: str = Field(description="The name of the single pipe to execute for each item in the input list.")

    input_list_name: Optional[str] = Field(
        default=None,
        description="The name of the list in the `WorkingMemory` to iterate over. "
        "If not provided, it defaults to the name of the `PipeBatch`'s main `input`.",
    )
    input_item_name: Optional[str] = Field(
        default=None,
        description="The name that an individual item from the list will have inside its execution branch. "
        "This is how the branch pipe finds its input.",
    )
