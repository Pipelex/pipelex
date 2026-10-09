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
        "input_item_name",
        [
            pytest.param("Item", id="pascal-case"),
            pytest.param("catalog.item", id="dotted"),
            pytest.param("_bound_item", id="the-reserved-prefix"),
            pytest.param("_item", id="underscore-led"),
            pytest.param("2nd_item", id="digit-led"),
        ],
    )
    def test_rejects_an_input_item_name_that_is_not_a_plain_input_name(self, input_item_name: str) -> None:
        """The batch stores each item under `input_item_name` for the branch pipe to read through an input, so it is a plain name."""
        with pytest.raises(ValidationError) as exc_info:
            PipeBatchBlueprint(
                description="Process each item",
                inputs={"items": "Item[]"},
                output="Result[]",
                branch_pipe_code="process_item",
                input_list_name="items",
                input_item_name=input_item_name,
            )
        refusals = [raw_error.get("ctx", {}).get("error") for raw_error in exc_info.value.errors()]
        assert len(refusals) == 1
        refusal = refusals[0]
        assert isinstance(refusal, PipeValidationError)
        assert refusal.error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert refusal.variable_names == [input_item_name]
        assert f"The PipeBatch's `input_item_name`, '{input_item_name}', is not a plain input name" in str(refusal)

    @pytest.mark.parametrize(
        "input_item_name",
        [
            pytest.param("item", id="a-plain-name"),
            pytest.param("bound_item", id="the-prefix-without-its-underscore"),
            pytest.param("item2", id="a-digit-after-the-first-letter"),
        ],
    )
    def test_accepts_a_plain_input_item_name(self, input_item_name: str) -> None:
        blueprint = PipeBatchBlueprint(
            description="Process each item",
            inputs={"items": "Item[]"},
            output="Result[]",
            branch_pipe_code="process_item",
            input_list_name="items",
            input_item_name=input_item_name,
        )

        assert blueprint.input_item_name == input_item_name

    def test_rejects_an_input_list_name_taking_the_reserved_prefix(self) -> None:
        """The list's name is a plain input name, which no underscore-led name is."""
        with pytest.raises(ValidationError) as exc_info:
            PipeBatchBlueprint(
                description="Process each item",
                inputs={"items": "Item[]"},
                output="Result[]",
                branch_pipe_code="process_item",
                input_list_name="_bound_items",
                input_item_name="item",
            )
        refusals = [raw_error.get("ctx", {}).get("error") for raw_error in exc_info.value.errors()]
        list_name_refusals = [
            refusal for refusal in refusals if isinstance(refusal, PipeValidationError) and refusal.variable_names == ["_bound_items"]
        ]
        assert len(list_name_refusals) == 1
        assert list_name_refusals[0].error_type == PipeValidationErrorType.INVALID_INPUT_NAME
        assert "is not a valid input name" in str(list_name_refusals[0])
