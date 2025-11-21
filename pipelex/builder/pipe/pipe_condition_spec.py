from typing import Literal

from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.tools.misc.pretty import PrettyPrintable


class PipeConditionSpec(PipeSpec):
    """PipeConditionSpec enables branching logic in pipelines by evaluating expressions
    and executing different pipes based on the results.

    Validation Rules:
        1. Either expression or expression_template should be provided, not both.
        2. outcomes map keys, must be strings representing possible valmes from expression.
        3. All values in outcomes map and default_outcome must be either valid pipe_code references or special outcomes "fail" or "continue".

    """

    type: SkipJsonSchema[Literal["PipeCondition"]] = "PipeCondition"
    pipe_category: SkipJsonSchema[Literal["PipeController"]] = "PipeController"
    jinja2_expression_template: str = Field(description="Jinja2 expression to evaluate.")
    outcomes: dict[str, str] = Field(..., description="Mapping `dict[str, str]` of condition to outcomes.")
    default_outcome: str | SpecialOutcome = Field(description="The fallback outcome if the expression result does not match any key in outcome map.")

    @field_validator("output", mode="after")
    @classmethod
    def forced_output(cls, _: str) -> str:
        return "native.Anything"

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with condition-specific details
        condition_group = Group()
        condition_group.renderables.append(base_group)

        # Add expression template in a panel
        condition_group.renderables.append(Text())  # Blank line
        expression_panel = Panel(
            self.jinja2_expression_template,
            title="Expression Template",
            title_align="left",
            border_style="yellow",
            padding=(0, 1),
        )
        condition_group.renderables.append(expression_panel)

        # Add outcomes as a table
        condition_group.renderables.append(Text())  # Blank line
        outcomes_table = Table(
            title="Outcomes:",
            title_justify="left",
            title_style="not italic",
            show_header=True,
            header_style="dim",
            show_edge=True,
            show_lines=True,
            border_style="dim",
        )
        outcomes_table.add_column("Condition", style="yellow")
        outcomes_table.add_column("Pipe", style="cyan")

        for condition, pipe in self.outcomes.items():
            outcomes_table.add_row(condition, pipe)

        condition_group.renderables.append(outcomes_table)

        # Add default outcome
        condition_group.renderables.append(Text())  # Blank line
        condition_group.renderables.append(Text.from_markup(f"Default Outcome: [bold red]{self.default_outcome}[/bold red]"))

        return condition_group

    @override
    def to_blueprint(self) -> PipeConditionBlueprint:
        base_blueprint = super().to_blueprint()
        return PipeConditionBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            pipe_category=self.pipe_category,
            expression_template=self.jinja2_expression_template,
            expression=None,
            outcomes=self.outcomes,
            default_outcome=self.default_outcome,
            add_alias_from_expression_to=None,
        )
