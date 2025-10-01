from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint


class PipeConditionTestCases:
    CONDITION_WITH_TEMPLATE = (
        "condition_with_template",
        PipeConditionSpec(
            the_pipe_code="template_condition",
            description="Conditional with template",
            inputs={"item": "Item"},
            output="ProcessedItem",
            jinja2_expression_template="{{ item.category }}",
            pipe_map={
                "A": "process_a",
                "B": "process_b",
                "C": "process_c",
            },
            default_pipe_code="process_default",
        ),
        PipeConditionBlueprint(
            description="Conditional with template",
            inputs={"item": InputRequirementBlueprint(concept="Item")},
            output="ProcessedItem",
            type="PipeCondition",
            category="PipeController",
            expression=None,
            expression_template="{{ item.category }}",
            pipe_map={
                "A": "process_a",
                "B": "process_b",
                "C": "process_c",
            },
            default_pipe_code="process_default",
            add_alias_from_expression_to=None,
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeConditionSpec, PipeConditionBlueprint]]] = [
        CONDITION_WITH_TEMPLATE,
    ]
