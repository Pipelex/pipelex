from typing import Literal, Self

from pydantic import Field, model_validator
from rich.console import Group
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable


class PipeBatchSpec(PipeSpec):
    """Spec for batch processing pipe operations concurrently.

    PipeBatch enables concurrent execution of the same pipe applied to multiple items
    provided as an input list. Each item is processed independently. The result is a list
    the results of each branch. So this like a map operation.

    Validation Rules:
        - There must be at least one input which is a list, corresponding to input_list_name.
          That name is typically a plural noun like "ideas" or "images".
          And the concept corresponding to that input list must be multiple, using the [] notation,
          i.e. something like "Ideas[]" or "Images[]".
        - input_item_name is typically the singular noun corresponding to the items in the list, like "idea" or "image".
        - input_item_name must NOT be the same as input_list_name.
        - input_item_name must NOT match any key in the inputs dict.

    """

    type: Literal["PipeBatch"] = "PipeBatch"
    pipe_category: Literal["PipeController"] = "PipeController"
    branch_pipe_code: str = Field(
        description="The pipe code to execute for each item in the input list. This pipe is instantiated once per item in parallel."
    )
    input_list_name: str = Field(
        description=(
            "Name of the list in WorkingMemory to iterate over. "
            "Typically a plural noun (e.g., 'items', 'reports'). "
            "Must match one of the keys in the inputs dict."
        ),
    )
    input_item_name: str = Field(
        description=(
            "Name assigned to individual items within each execution branch. "
            "Typically the singular form of input_list_name (e.g., 'item', 'report'). "
            "Must NOT be the same as input_list_name or any key in the inputs dict."
        ),
    )

    @model_validator(mode="after")
    def validate_input_names(self) -> Self:
        """Validate that input_item_name does not collide with input_list_name or inputs keys."""
        if self.input_item_name == self.input_list_name:
            msg = (
                f"input_item_name '{self.input_item_name}' must not be the same as input_list_name "
                f"'{self.input_list_name}'. The list name should be plural (e.g., 'reports') and "
                f"the item name should be the singular form (e.g., 'report')."
            )
            raise ValueError(msg)
        if self.inputs and self.input_item_name in self.inputs:
            msg = (
                f"input_item_name '{self.input_item_name}' must not be the same as any key in inputs "
                f"(found in: {list(self.inputs.keys())}). "
                f"The input_item_name is injected into the branch pipe for each iteration "
                f"and must be distinct from the batch pipe's own input names. "
                f"Use the singular form of the list name (e.g., 'reports' → 'report')."
            )
            raise ValueError(msg)
        return self

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with batch-specific details
        batch_group = Group()
        batch_group.renderables.append(base_group)

        # Add batch-specific information
        batch_group.renderables.append(Text())  # Blank line
        batch_group.renderables.append(Text.from_markup(f"Branch Pipe: [red]{self.branch_pipe_code}[/red]"))
        batch_group.renderables.append(Text.from_markup(f"Iterate Over: [bold cyan]{self.input_list_name}[/bold cyan]"))
        batch_group.renderables.append(Text.from_markup(f"Item Name: [cyan]{self.input_item_name}[/cyan]"))

        return batch_group

    @override
    def to_blueprint(self) -> PipeBatchBlueprint:
        base_blueprint = super().to_blueprint()
        return PipeBatchBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs_concept_specs,
            output=base_blueprint.output,
            branch_pipe_code=self.branch_pipe_code,
            input_list_name=self.input_list_name,
            input_item_name=self.input_item_name,
        )
