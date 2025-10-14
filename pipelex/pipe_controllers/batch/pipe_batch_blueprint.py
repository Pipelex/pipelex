from typing import Literal

from typing_extensions import override

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeBatchBlueprint(PipeBlueprint):
    type: Literal["PipeBatch"] = "PipeBatch"
    pipe_category: Literal["PipeController"] = "PipeController"
    branch_pipe_code: str
    input_list_name: str | None = None
    input_item_name: str | None = None

    @property
    @override
    def pipe_dependencies(self) -> set[str]:
        """Return the set containing the branch pipe code."""
        return {self.branch_pipe_code}
