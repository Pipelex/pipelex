from typing import Any, ClassVar

from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome


class PipeConditionInputTestCases:
    """Test cases for PipeCondition input validation."""

    # Valid test cases: (test_id, blueprint)
    VALID_WITH_EXPRESSION: ClassVar[tuple[str, PipeConditionBlueprint]] = (
        "valid_with_expression",
        PipeConditionBlueprint(
            description="Test case: valid_with_expression",
            inputs={"status": "native.Text"},
            output="native.Text",
            expression="status",
            outcomes={"approved": "approve_pipe", "rejected": "reject_pipe"},
            default_outcome="fallback_pipe",
        ),
    )

    VALID_WITH_EXPRESSION_TEMPLATE: ClassVar[tuple[str, PipeConditionBlueprint]] = (
        "valid_with_expression_template",
        PipeConditionBlueprint(
            description="Test case: valid_with_expression_template",
            inputs={"category": "native.Text"},
            output="native.Text",
            expression_template="{{ category }}",
            outcomes={"small": "process_small", "large": "process_large"},
            default_outcome="process_default",
        ),
    )

    VALID_WITH_MULTIPLE_OUTCOMES: ClassVar[tuple[str, PipeConditionBlueprint]] = (
        "valid_with_multiple_outcomes",
        PipeConditionBlueprint(
            description="Test case: valid_with_multiple_outcomes",
            inputs={"priority": "native.Text"},
            output="native.Text",
            expression="priority",
            outcomes={
                "high": "urgent_handler",
                "medium": "normal_handler",
                "low": "delayed_handler",
            },
            default_outcome="default_handler",
        ),
    )

    VALID_WITH_SPECIAL_OUTCOME: ClassVar[tuple[str, PipeConditionBlueprint]] = (
        "valid_with_special_outcome",
        PipeConditionBlueprint(
            description="Test case: valid_with_special_outcome",
            inputs={"should_process": "native.Text"},
            output="native.Text",
            expression="should_process",
            outcomes={"yes": "process_pipe"},
            default_outcome=SpecialOutcome.CONTINUE,
        ),
    )

    VALID_WITH_ALIAS: ClassVar[tuple[str, PipeConditionBlueprint]] = (
        "valid_with_alias",
        PipeConditionBlueprint(
            description="Test case: valid_with_alias",
            inputs={"type": "native.Text"},
            output="native.Text",
            expression="type",
            outcomes={"A": "handle_a", "B": "handle_b"},
            default_outcome="handle_default",
            add_alias_from_expression_to="selected_type",
        ),
    )

    VALID_SINGLE_OUTCOME: ClassVar[tuple[str, PipeConditionBlueprint]] = (
        "valid_single_outcome",
        PipeConditionBlueprint(
            description="Test case: valid_single_outcome",
            inputs={"flag": "native.Text"},
            output="native.Text",
            expression="flag",
            outcomes={"true": "process_pipe"},
            default_outcome=SpecialOutcome.CONTINUE,
        ),
    )

    VALID_CASES: ClassVar[list[tuple[str, PipeConditionBlueprint]]] = [
        VALID_WITH_EXPRESSION,
        VALID_WITH_EXPRESSION_TEMPLATE,
        VALID_WITH_MULTIPLE_OUTCOMES,
        VALID_WITH_SPECIAL_OUTCOME,
        VALID_WITH_ALIAS,
        VALID_SINGLE_OUTCOME,
    ]

    # Error test cases: (test_id, blueprint_dict, expected_error_message_fragment)
    # Using dicts instead of blueprints to avoid validation errors during import
    ERROR_BOTH_EXPRESSION_AND_TEMPLATE: ClassVar[tuple[str, dict[str, Any], str]] = (
        "both_expression_and_template",
        {
            "description": "Test case: both_expression_and_template",
            "inputs": {"data": "native.Text"},
            "output": "native.Text",
            "expression": "data",
            "expression_template": "{{ data }}",
            "outcomes": {"A": "pipe_a"},
            "default_outcome": "pipe_default",
        },
        "exactly one of expression_template or expression",
    )

    ERROR_NEITHER_EXPRESSION_NOR_TEMPLATE: ClassVar[tuple[str, dict[str, Any], str]] = (
        "neither_expression_nor_template",
        {
            "description": "Test case: neither_expression_nor_template",
            "inputs": {"data": "native.Text"},
            "output": "native.Text",
            "expression": None,
            "expression_template": None,
            "outcomes": {"A": "pipe_a"},
            "default_outcome": "pipe_default",
        },
        "exactly one of expression_template or expression",
    )

    ERROR_EMPTY_OUTCOMES: ClassVar[tuple[str, dict[str, Any], str]] = (
        "empty_outcomes",
        {
            "description": "Test case: empty_outcomes",
            "inputs": {"data": "native.Text"},
            "output": "native.Text",
            "expression": "data",
            "outcomes": {},
            "default_outcome": "pipe_default",
        },
        "must have at least one mapping in outcomes",
    )

    ERROR_CASES: ClassVar[list[tuple[str, dict[str, Any], str]]] = [
        ERROR_BOTH_EXPRESSION_AND_TEMPLATE,
        ERROR_NEITHER_EXPRESSION_NOR_TEMPLATE,
        ERROR_EMPTY_OUTCOMES,
    ]
