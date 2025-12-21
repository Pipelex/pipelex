from typing import Literal

from pydantic import Field, field_validator, model_validator
from rich.console import Group
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.core.concepts.validation import validate_concept_ref_or_code
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.types import Self


class PipeParallelSpec(PipeSpec):
    """Spec for parallel pipe execution in the Pipelex framework.

    PipeParallel enables concurrent execution of multiple pipes, improving performance
    for independent operations. All parallel pipes receive the same input context
    and their outputs can be combined or kept separate.

    Validation Rules:
        1. Parallels list must not be empty.
        2. Each parallel step must be a valid SubPipeSpec.
        3. combined_output, when specified, must be a valid ConceptCode in PascalCase.
        4. Pipe codes in parallels must reference existing pipes (snake_case).

    """

    type: Literal["PipeParallel"] = "PipeParallel"
    pipe_category: Literal["PipeController"] = "PipeController"
    parallels: list[SubPipeSpec] = Field(description="List of SubPipeSpec instances to execute concurrently.")
    add_each_output: bool = Field(description="Whether to include individual pipe outputs in the combined result.")
    combined_output: str | None = Field(default=None, description="Optional ConceptCode in PascalCasefor the combined output structure.")

    @field_validator("combined_output", mode="before")
    @classmethod
    def validate_combined_output(cls, combined_output: str) -> str:
        if combined_output:
            validate_concept_ref_or_code(concept_ref_or_code=combined_output)
        return combined_output

    @model_validator(mode="after")
    def validate_output_options(self) -> Self:
        if not self.add_each_output and not self.combined_output:
            msg = (
                "PipeParallel requires either add_each_output to be True or combined_output to be set, "
                "or both, otherwise the pipe won't output anything"
            )
            raise ValueError(msg)
        return self

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with parallel-specific details
        parallel_group = Group()
        parallel_group.renderables.append(base_group)

        # Add parallel configuration
        parallel_group.renderables.append(Text())  # Blank line
        parallel_group.renderables.append(Text.from_markup(f"Add Each Output: [bold yellow]{self.add_each_output}[/bold yellow]"))
        if self.combined_output:
            parallel_group.renderables.append(Text.from_markup(f"Combined Output: [bold green]{self.combined_output}[/bold green]"))

        # Add parallel branches as a table
        parallel_group.renderables.append(Text())  # Blank line
        parallels_table = Table(
            title="Parallel Branches:",
            title_justify="left",
            title_style="not italic",
            show_header=True,
            header_style="dim",
            show_edge=True,
            show_lines=True,
            border_style="dim",
        )
        parallels_table.add_column("Branch", style="dim", width=6, justify="right")
        parallels_table.add_column("Pipe", style="red")
        parallels_table.add_column("Result name", style="cyan")

        for idx, parallel in enumerate(self.parallels, start=1):
            parallels_table.add_row(str(idx), parallel.pipe_code, parallel.result)

        parallel_group.renderables.append(parallels_table)

        return parallel_group

    @override
    def to_blueprint(self) -> PipeParallelBlueprint:
        base_blueprint = super().to_blueprint()
        core_parallels = [parallel.to_blueprint() for parallel in self.parallels]
        return PipeParallelBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            pipe_category=self.pipe_category,
            parallels=core_parallels,
            add_each_output=self.add_each_output,
            combined_output=self.combined_output,
        )
