from typing import Literal

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeBatchBlueprint(PipeBlueprint):
    type: Literal["PipeBatch"] = "PipeBatch"
    category: Literal["PipeController"] = "PipeController"
    branch_pipe_code: str
    input_list_name: str | None = None
    input_item_name: str | None = None
