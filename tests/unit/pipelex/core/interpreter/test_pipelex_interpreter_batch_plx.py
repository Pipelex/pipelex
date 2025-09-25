import pytest

from pipelex.core.interpreter import PipelexInterpreter
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint


class TestPipelexInterpreterBatchPLX:
    @pytest.mark.parametrize(
        "pipe_name,blueprint,expected_plx",
        [
            # Basic Batch pipe
            (
                "batch_process",
                PipeBatchBlueprint(
                    type="PipeBatch",
                    definition="Process items in batch",
                    output="ProcessedData",
                    branch_pipe_code="process_item",
                    input_list_name="items",
                    input_item_name="current_item",
                ),
                """[pipe.batch_process]
type = "PipeBatch"
definition = "Process items in batch"
output = "ProcessedData"
branch_pipe_code = "process_item"
input_list_name = "items"
input_item_name = "current_item\"""",
            ),
            # Batch pipe with inputs
            (
                "batch_with_inputs",
                PipeBatchBlueprint(
                    type="PipeBatch",
                    definition="Batch processing with inputs",
                    inputs={"data_list": "Text", "config": "Text"},
                    output="ProcessedData",
                    branch_pipe_code="transform_item",
                ),
                """[pipe.batch_with_inputs]
type = "PipeBatch"
definition = "Batch processing with inputs"
inputs = { data_list = "Text", config = "Text" }
output = "ProcessedData"
branch_pipe_code = "transform_item\"""",
            ),
        ],
    )
    def test_batch_pipe_to_plx_string(self, pipe_name: str, blueprint: PipeBatchBlueprint, expected_plx: str):
        """Test converting Batch pipe blueprint to PLX string."""
        result = PipelexInterpreter.batch_pipe_to_plx_string(pipe_name, blueprint)
        assert result == expected_plx
