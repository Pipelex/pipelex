import pytest
from pydantic import ValidationError

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.validation_error_types import PipeValidationErrorType


class TestPipeBatchValidation:
    def test_accepts_valid_batch_config(self):
        """Valid PipeBatch config passes validation."""
        blueprint = PipeBatchBlueprint(
            description="Process each item",
            inputs={"items": "Item[]", "context": "Text"},
            output="Result[]",
            branch_pipe_code="process_item",
            input_list_name="items",
            input_item_name="item",
        )
        assert blueprint.input_item_name == "item"
        assert blueprint.input_list_name == "items"

    def test_rejects_input_item_name_same_as_input_list_name(self):
        """Blueprint validation rejects input_item_name == input_list_name with PipeValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            PipeBatchBlueprint(
                description="Process each item",
                inputs={"items": "Item[]"},
                output="Result[]",
                branch_pipe_code="process_item",
                input_list_name="items",
                input_item_name="items",
            )
        error_str = str(exc_info.value)
        assert "must not be the same as input list name" in error_str
        # Verify the underlying error is a PipeValidationError with the correct type
        raw_errors = exc_info.value.errors()
        assert len(raw_errors) == 1
        ctx = raw_errors[0].get("ctx", {})
        original_error = ctx.get("error")
        assert isinstance(original_error, PipeValidationError)
        assert original_error.error_type == PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION

    def test_rejects_input_item_name_in_inputs(self):
        """Blueprint validation rejects input_item_name that shadows an inputs key."""
        with pytest.raises(ValidationError) as exc_info:
            PipeBatchBlueprint(
                description="Process each item",
                inputs={"items": "Item[]", "context": "Text"},
                output="Result[]",
                branch_pipe_code="process_item",
                input_list_name="items",
                input_item_name="context",
            )
        error_str = str(exc_info.value)
        assert "must not be the same as any key in inputs" in error_str
        raw_errors = exc_info.value.errors()
        assert len(raw_errors) == 1
        ctx = raw_errors[0].get("ctx", {})
        original_error = ctx.get("error")
        assert isinstance(original_error, PipeValidationError)
        assert original_error.error_type == PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION

    def test_rejects_missing_input_list_name(self):
        """Blueprint validation rejects when input_list_name is not in inputs."""
        with pytest.raises(ValidationError, match="Input list name"):
            PipeBatchBlueprint(
                description="Process each item",
                inputs={"other": "Text"},
                output="Result[]",
                branch_pipe_code="process_item",
                input_list_name="items",
                input_item_name="item",
            )

    def test_rejects_empty_input_item_name(self):
        """Blueprint validation rejects empty input_item_name."""
        with pytest.raises(ValidationError, match="Empty input item name"):
            PipeBatchBlueprint(
                description="Process each item",
                inputs={"items": "Item[]"},
                output="Result[]",
                branch_pipe_code="process_item",
                input_list_name="items",
                input_item_name="",
            )

    @pytest.mark.parametrize(
        ("input_list_name", "input_item_name", "reserved_name", "message_fragment"),
        [
            pytest.param(
                "items",
                "_bound_item",
                "_bound_item",
                "The PipeBatch's `input_item_name`, '_bound_item', takes the `_bound_` prefix, which is reserved for the bound list of a "
                "dotted `batch_over`",
                id="input-item-name",
            ),
            pytest.param("_bound_items", "item", "_bound_items", "is not a valid input name", id="input-list-name"),
        ],
    )
    def test_rejects_a_name_taking_the_reserved_prefix(
        self, input_list_name: str, input_item_name: str, reserved_name: str, message_fragment: str
    ) -> None:
        """The batch writes its item into the branch's memory under its own name, so the runtime's `_bound_` prefix is refused there too."""
        with pytest.raises(ValidationError) as exc_info:
            PipeBatchBlueprint(
                description="Process each item",
                inputs={"items": "Item[]"},
                output="Result[]",
                branch_pipe_code="process_item",
                input_list_name=input_list_name,
                input_item_name=input_item_name,
            )
        refusals = [raw_error.get("ctx", {}).get("error") for raw_error in exc_info.value.errors()]
        reserved_name_refusals = [
            refusal for refusal in refusals if isinstance(refusal, PipeValidationError) and refusal.variable_names == [reserved_name]
        ]
        assert len(reserved_name_refusals) == 1
        assert reserved_name_refusals[0].error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert message_fragment in str(reserved_name_refusals[0])
