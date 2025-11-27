from typing import Literal

from pydantic import Field
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

    """

    type: Literal["PipeBatch"] = "PipeBatch"
    pipe_category: Literal["PipeController"] = "PipeController"
    branch_pipe_code: str = Field(
        description="The pipe code to execute for each item in the input list. This pipe is instantiated once per item in parallel."
    )
    input_list_name: str = Field(description="Name of the list in WorkingMemory to iterate over, if needed.")
    input_item_name: str = Field(
        description="Name assigned to individual items within each execution branch. This is how the branch pipe accesses its specific input item.",
    )

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
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
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            branch_pipe_code=self.branch_pipe_code,
            input_list_name=self.input_list_name,
            input_item_name=self.input_item_name,
        )
