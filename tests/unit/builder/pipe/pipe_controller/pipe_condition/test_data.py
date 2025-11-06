from typing import ClassVar

from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint


class PipeConditionTestCases:
    CONDITION_WITH_TEMPLATE = (
        "condition_with_template",
        PipeConditionSpec(
            pipe_code="template_condition",
            description="Conditional with template",
            inputs={"item": "Item"},
            output="ProcessedItem",
            jinja2_expression_template="{{ item.category }}",
            outcomes={
                "A": "process_a",
                "B": "process_b",
                "C": "process_c",
            },
            default_outcome="process_default",
        ),
        PipeConditionBlueprint(
            description="Conditional with template",
            inputs={"item": "Item"},
            output="ProcessedItem",
            type="PipeCondition",
            pipe_category="PipeController",
            expression=None,
            expression_template="{{ item.category }}",
            outcomes={
                "A": "process_a",
                "B": "process_b",
                "C": "process_c",
            },
            default_outcome="process_default",
            add_alias_from_expression_to=None,
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeConditionSpec, PipeConditionBlueprint]]] = [
        CONDITION_WITH_TEMPLATE,
    ]
