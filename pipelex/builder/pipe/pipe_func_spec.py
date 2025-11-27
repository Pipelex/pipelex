from typing import Literal

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema
from rich.console import Group
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable


class PipeFuncSpec(PipeSpec):
    """PipeFunc enables calling custom functions in the Pipelex framework."""

    type: SkipJsonSchema[Literal["PipeFunc"]] = "PipeFunc"
    pipe_category: SkipJsonSchema[Literal["PipeOperator"]] = "PipeOperator"
    function_name: str = Field(description="The name of the function to call.")

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with func-specific details
        func_group = Group()
        func_group.renderables.append(base_group)

        # Add function specific information
        func_group.renderables.append(Text())  # Blank line
        func_group.renderables.append(Text.from_markup(f"Function Name: [bold cyan]{self.function_name}[/bold cyan]"))

        return func_group

    @override
    def to_blueprint(self) -> PipeFuncBlueprint:
        base_blueprint = super().to_blueprint()
        return PipeFuncBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            function_name=self.function_name,
        )
