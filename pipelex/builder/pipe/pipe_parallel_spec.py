from typing import Literal

from pydantic import Field
from rich.console import Group
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable


class PipeParallelSpec(PipeSpec):
    """Spec for parallel pipe execution in the Pipelex framework.

    PipeParallel enables concurrent execution of multiple pipes, improving performance
    for independent operations. All parallel pipes receive the same input context.
    Their outputs are always combined into the pipe's declared output concept — either
    `Composite` (untyped named composition) or a structured concept whose fields
    correspond to the branch result names.

    Validation Rules:
        1. Branches list must not be empty.
        2. Each branch must be a valid SubPipeSpec.
        3. Pipe codes in branches must reference existing pipes (snake_case).
        4. The output must be `Composite` or a structured concept compatible with the
           branch result names (validated at the blueprint/library level).

    """

    type: Literal["PipeParallel"] = "PipeParallel"
    pipe_category: Literal["PipeController"] = "PipeController"
    branches: list[SubPipeSpec] = Field(description="List of SubPipeSpec instances to execute concurrently.")
    add_each_output: bool = Field(description="Whether to also expose each branch output by its result name in memory.")

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with parallel-specific details
        parallel_group = Group()
        parallel_group.renderables.append(base_group)

        # Add parallel configuration
        parallel_group.renderables.append(Text())  # Blank line
        parallel_group.renderables.append(Text.from_markup(f"Add Each Output: [bold yellow]{self.add_each_output}[/bold yellow]"))

        # Add parallel branches as a table
        parallel_group.renderables.append(Text())  # Blank line
        branches_table = Table(
            title="Parallel Branches:",
            title_justify="left",
            title_style="not italic",
            show_header=True,
            header_style="dim",
            show_edge=True,
            show_lines=True,
            border_style="dim",
        )
        branches_table.add_column("Branch", style="dim", width=6, justify="right")
        branches_table.add_column("Pipe", style="red")
        branches_table.add_column("Result name", style="cyan")

        for idx, branch in enumerate(self.branches, start=1):
            branches_table.add_row(str(idx), branch.pipe_code, branch.result)

        parallel_group.renderables.append(branches_table)

        return parallel_group

    @override
    def to_blueprint(self) -> PipeParallelBlueprint:
        base_blueprint = super().to_blueprint()
        core_branches = [branch.to_blueprint() for branch in self.branches]
        return PipeParallelBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            pipe_category=self.pipe_category,
            branches=core_branches,
            add_each_output=self.add_each_output,
        )
