import pytest
from pydantic import ValidationError

from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from tests.unit.pipelex.builder.pipe.pipe_controller.pipe_batch.test_data import PipeBatchTestCases


class TestPipeBatchBlueprintConversion:
    @pytest.mark.parametrize(
        ("test_name", "pipe_spec", "expected_blueprint"),
        PipeBatchTestCases.TEST_CASES,
    )
    def test_pipe_batch_spec_to_blueprint(
        self,
        test_name: str,  # ruff: ignore[unused-method-argument]
        pipe_spec: PipeBatchSpec,
        expected_blueprint: PipeBatchBlueprint,
    ):
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint

    def test_rejects_input_item_name_same_as_input_list_name(self):
        """Spec-level validation rejects input_item_name == input_list_name."""
        with pytest.raises(ValidationError, match="input_item_name"):
            PipeBatchSpec(
                pipe_code="batch_items",
                description="Batch with collision",
                inputs={"items": "Item[]"},
                output="Result[]",
                branch_pipe_code="process_item",
                input_list_name="items",
                input_item_name="items",
            )

    def test_rejects_input_item_name_same_as_inputs_key(self):
        """Spec-level validation rejects input_item_name that shadows an inputs key."""
        with pytest.raises(ValidationError, match="input_item_name"):
            PipeBatchSpec(
                pipe_code="batch_items",
                description="Batch with collision",
                inputs={"items": "Item[]", "context": "Text"},
                output="Result[]",
                branch_pipe_code="process_item",
                input_list_name="items",
                input_item_name="context",
            )
