from typing import Literal, Optional

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeBatchBlueprint(PipeBlueprint):
    type: Literal["PipeBatch"] = "PipeBatch"
    branch_pipe_code: str

    input_list_name: Optional[str] = None
    input_item_name: Optional[str] = None
