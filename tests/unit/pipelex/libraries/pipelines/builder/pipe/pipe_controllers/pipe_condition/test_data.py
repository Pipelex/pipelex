from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.inputs_spec import InputRequirementSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_condition_spec import PipeConditionPipeMapSpec, PipeConditionSpec
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint, PipeConditionPipeMapBlueprint


class PipeConditionTestCases:
    SIMPLE_CONDITION = (
        "simple_condition",
        PipeConditionSpec(
            the_pipe_code="conditional_processor",
            definition="Choose pipe based on condition",
            inputs={"data": InputRequirementSpec(concept="Data")},
            output="Result",
            expression="data.status",
            pipe_map=PipeConditionPipeMapSpec(
                root={
                    "active": "process_active",
                    "inactive": "process_inactive",
                },
            ),
        ),
        PipeConditionBlueprint(
            definition="Choose pipe based on condition",
            inputs={"data": InputRequirementBlueprint(concept="Data")},
            output="Result",
            type="PipeCondition",
            category="PipeController",
            expression="data.status",
            expression_template=None,
            pipe_map=PipeConditionPipeMapBlueprint(
                root={
                    "active": "process_active",
                    "inactive": "process_inactive",
                },
            ),
            default_pipe_code=None,
            add_alias_from_expression_to=None,
        ),
    )

    CONDITION_WITH_TEMPLATE = (
        "condition_with_template",
        PipeConditionSpec(
            the_pipe_code="template_condition",
            definition="Conditional with template",
            inputs={"item": InputRequirementSpec(concept="Item")},
            output="ProcessedItem",
            expression_template="{{ item.category }}",
            pipe_map=PipeConditionPipeMapSpec(
                root={
                    "A": "process_a",
                    "B": "process_b",
                    "C": "process_c",
                },
            ),
            default_pipe_code="process_default",
            add_alias_from_expression_to="category_result",
        ),
        PipeConditionBlueprint(
            definition="Conditional with template",
            inputs={"item": InputRequirementBlueprint(concept="Item")},
            output="ProcessedItem",
            type="PipeCondition",
            category="PipeController",
            expression=None,
            expression_template="{{ item.category }}",
            pipe_map=PipeConditionPipeMapBlueprint(
                root={
                    "A": "process_a",
                    "B": "process_b",
                    "C": "process_c",
                },
            ),
            default_pipe_code="process_default",
            add_alias_from_expression_to="category_result",
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeConditionSpec, PipeConditionBlueprint]]] = [
        SIMPLE_CONDITION,
        CONDITION_WITH_TEMPLATE,
    ]
