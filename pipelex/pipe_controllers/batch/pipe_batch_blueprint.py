from typing import Literal

from typing_extensions import override

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeBatchBlueprint(PipeBlueprint):
    type: Literal["PipeBatch"] = "PipeBatch"
    pipe_category: Literal["PipeController"] = "PipeController"
    branch_pipe_code: str
    input_list_name: str
    input_item_name: str

    @property
    @override
    def pipe_dependencies(self) -> set[str]:
        """Return the set containing the branch pipe code."""
        return {self.branch_pipe_code}

    @override
    def validate_inputs(self):
        # The PipeBatch will iterate over a list and pass each item to the branch pipe,
        # so we must have the list's name as part of the batch inputs
        # and conversely, we must not have the item's name as part of the batch inputs
        if not self.inputs or self.input_list_name not in self.inputs:
            msg = f"Input list name '{self.input_list_name}' not found in inputs: {self.inputs}"
            raise ValueError(msg)
        if not self.input_item_name:
            msg = "Empty input item name is not allowed"
            raise ValueError(msg)
        if self.input_item_name in self.inputs:
            msg = f"Input item name '{self.input_item_name}' found in inputs: {self.inputs}"
            raise ValueError(msg)

    @override
    def validate_output(self):
        pass
