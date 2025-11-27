from typing import Literal

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema
from rich.console import Group
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable


class PipeSequenceSpec(PipeSpec):
    """PipeSequenceSpec orchestrates the execution of multiple pipes in a defined order,
    where each pipe's output can be used as input for subsequent pipes. This enables
    building complex data processing workflows with step-by-step transformations.
    """

    type: SkipJsonSchema[Literal["PipeSequence"]] = "PipeSequence"
    pipe_category: SkipJsonSchema[Literal["PipeController"]] = "PipeController"
    steps: list[SubPipeSpec] = Field(
        description=("List of SubPipeSpec instances to execute sequentially. Each step runs after the previous one completes.")
    )

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with sequence-specific details
        sequence_group = Group()
        sequence_group.renderables.append(base_group)

        # Add sequence steps as a table
        sequence_group.renderables.append(Text())  # Blank line
        steps_table = Table(
            title="Sequence Steps:",
            title_justify="left",
            title_style="not italic",
            show_header=True,
            header_style="dim",
            show_edge=True,
            show_lines=True,
            border_style="dim",
        )
        steps_table.add_column("Step", style="dim", width=4, justify="right")
        steps_table.add_column("Pipe", style="red")
        steps_table.add_column("Result name", style="cyan")

        for idx, step in enumerate(self.steps, start=1):
            steps_table.add_row(str(idx), step.pipe_code, step.result)

        sequence_group.renderables.append(steps_table)

        return sequence_group

    @override
    def to_blueprint(self) -> PipeSequenceBlueprint:
        base_blueprint = super().to_blueprint()
        core_steps = [step.to_blueprint() for step in self.steps]
        return PipeSequenceBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            steps=core_steps,
        )
