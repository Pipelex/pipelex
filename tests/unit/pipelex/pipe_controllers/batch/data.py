from typing import ClassVar

from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint


class PipeBatchInputTestCases:
    """Test cases for PipeBatch input validation."""

    # Valid test cases: (test_id, blueprint)
    VALID_SIMPLE_BATCH: ClassVar[tuple[str, PipeBatchBlueprint]] = (
        "valid_simple_batch",
        PipeBatchBlueprint(
            description="Test case: valid_simple_batch",
            inputs={"items": "native.Text"},
            output="native.Text",
            branch_pipe_code="process_item",
            input_list_name="items",
            input_item_name="item",
        ),
    )

    VALID_MULTIPLE_INPUTS: ClassVar[tuple[str, PipeBatchBlueprint]] = (
        "valid_multiple_inputs",
        PipeBatchBlueprint(
            description="Test case: valid_multiple_inputs",
            inputs={"items": "native.Text", "config": "native.Text"},
            output="native.Text",
            branch_pipe_code="process_with_config",
            input_list_name="items",
            input_item_name="item",
        ),
    )

    VALID_CASES: ClassVar[list[tuple[str, PipeBatchBlueprint]]] = [
        VALID_SIMPLE_BATCH,
        VALID_MULTIPLE_INPUTS,
    ]
