"""
Test data for PipeConditionBlueprint conversion tests.
"""

from typing import ClassVar, List, Tuple

from pipelex.core.pipes.pipe_input_spec_blueprint import (
    InputRequirementBlueprint as InputRequirementBlueprintCore,
)
from pipelex.libraries.pipelines.builder.pipe.inputs import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_condition_builder import (
    PipeConditionBlueprint,
    PipeConditionPipeMapBlueprint,
)
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import (
    PipeConditionBlueprint as PipeConditionBlueprintCore,
)
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import (
    PipeConditionPipeMapBlueprint as PipeConditionPipeMapBlueprintCore,
)


class PipeConditionTestCases:
    """Test cases for PipeConditionBlueprint conversion."""

    SIMPLE_CONDITION = (
        "simple_condition",
        PipeConditionBlueprint(
            definition="Choose pipe based on condition",
            inputs={"data": InputRequirementBlueprint(concept="Data")},
            output="Result",
            expression="data.status",
            pipe_map=PipeConditionPipeMapBlueprint(
                root={
                    "active": "process_active",
                    "inactive": "process_inactive",
                }
            ),
        ),
        "conditional_processor",
        "test_domain",
        PipeConditionBlueprintCore(
            definition="Choose pipe based on condition",
            inputs={"data": InputRequirementBlueprintCore(concept="Data")},
            output="Result",
            type="PipeCondition",
            category="PipeController",
            expression="data.status",
            expression_template=None,
            pipe_map=PipeConditionPipeMapBlueprintCore(
                root={
                    "active": "process_active",
                    "inactive": "process_inactive",
                }
            ),
            default_pipe_code=None,
            add_alias_from_expression_to=None,
        ),
    )

    CONDITION_WITH_TEMPLATE = (
        "condition_with_template",
        PipeConditionBlueprint(
            definition="Conditional with template",
            inputs={"item": InputRequirementBlueprint(concept="Item")},
            output="ProcessedItem",
            expression_template="{{ item.category }}",
            pipe_map=PipeConditionPipeMapBlueprint(
                root={
                    "A": "process_a",
                    "B": "process_b",
                    "C": "process_c",
                }
            ),
            default_pipe_code="process_default",
            add_alias_from_expression_to="category_result",
        ),
        "template_condition",
        "test_domain",
        PipeConditionBlueprintCore(
            definition="Conditional with template",
            inputs={"item": InputRequirementBlueprintCore(concept="Item")},
            output="ProcessedItem",
            type="PipeCondition",
            category="PipeController",
            expression=None,
            expression_template="{{ item.category }}",
            pipe_map=PipeConditionPipeMapBlueprintCore(
                root={
                    "A": "process_a",
                    "B": "process_b",
                    "C": "process_c",
                }
            ),
            default_pipe_code="process_default",
            add_alias_from_expression_to="category_result",
        ),
    )

    TEST_CASES: ClassVar[List[Tuple[str, PipeConditionBlueprint, str, str, PipeConditionBlueprintCore]]] = [
        SIMPLE_CONDITION,
        CONDITION_WITH_TEMPLATE,
    ]
