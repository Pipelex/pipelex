from typing import Dict, Literal, Optional

from pydantic import Field, RootModel

from pipelex.libraries.pipelines.builder.pipe.pipe import PipeBlueprint

PipeConditionPipeMapRoot = Dict[str, str]


class PipeConditionPipeMapBlueprint(RootModel[PipeConditionPipeMapRoot]):
    """Blueprint for condition-to-pipe mapping in PipeCondition.

    Maps condition values to pipe codes for conditional execution.

    Attributes:
        root: Dictionary mapping condition results (keys) to pipe codes (values).
              Each key represents a possible condition outcome, and its value
              is the pipe code to execute when that condition is met.
    """

    root: PipeConditionPipeMapRoot = Field(default_factory=dict)


class PipeConditionBlueprint(PipeBlueprint):
    """Blueprint for conditional pipe execution in the Pipelex framework.

    PipeCondition enables branching logic in pipelines by evaluating expressions
    and executing different pipes based on the results. Supports template-based
    and direct expression evaluation with default fallback options.

    Attributes:
        type: Fixed to "PipeCondition" for this pipe type.
        expression_template: Template for building the expression to evaluate.
                           Supports variable substitution for dynamic conditions.
        expression: Direct expression to evaluate. Typically uses the result
                   of the previous pipe. Mutually exclusive with expression_template.
        pipe_map: Mapping of condition results to pipe codes. Each condition
                 outcome triggers execution of its associated pipe.
        default_pipe_code: Fallback pipe to execute when no conditions in pipe_map
                          match the expression result.
        add_alias_from_expression_to: Optional name to store the expression result
                                     in the context for later reference.

    Validation Rules:
        1. Either expression or expression_template should be provided, not both.
        2. pipe_map keys must be strings representing possible condition outcomes.
        3. All pipe codes in pipe_map and default_pipe_code must be valid pipe references.

    Raises:
        PipeDefinitionError: When validation rules are violated.
    """

    type: Literal["PipeCondition"] = "PipeCondition"
    expression_template: Optional[str] = None
    expression: Optional[str] = None
    pipe_map: PipeConditionPipeMapBlueprint = Field(default_factory=PipeConditionPipeMapBlueprint)
    default_pipe_code: Optional[str] = None
    add_alias_from_expression_to: Optional[str] = None


class PipeConditionSpecBlueprint(PipeConditionBlueprint):
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
