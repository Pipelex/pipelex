from typing import Literal

from typing_extensions import override

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint
from pipelex.validation_error_types import PipeValidationErrorType


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
        # Specialization: catch the most common mistake (item name == list name) with a targeted message
        if self.input_item_name == self.input_list_name:
            msg = (
                f"Input item name '{self.input_item_name}' must not be the same as "
                f"input list name '{self.input_list_name}'. "
                f"Use a plural for the list and its singular form for the item "
                f"(e.g., list 'reports' → item 'report')."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION,
            )
        # General guard: item name must not collide with any other input key either
        # (e.g. a batch pipe with inputs {"items": "Item[]", "context": "Text"} must not use "context" as item name)
        if self.input_item_name in self.inputs:
            msg = (
                f"Input item name '{self.input_item_name}' must not be the same as any key in inputs: "
                f"{self.inputs}. The input_item_name is injected into the branch pipe for each iteration. "
                f"Use the singular form of the list name "
                f"(e.g., list 'reports' → item 'report')."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION,
            )

    @override
    def validate_output(self):
        pass
