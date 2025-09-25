from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint

PIPE_BATCH = (
    "pipe_batch",
    """domain = "test_pipes"
definition = "Domain with batch pipe"

[pipe.batch_process]
type = "PipeBatch"
definition = "Process items in batch"
output = "ProcessedData"
branch_pipe_code = "process_item"
input_list_name = "items"
input_item_name = "current_item"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with batch pipe",
        pipe={
            "batch_process": PipeBatchBlueprint(
                type="PipeBatch",
                definition="Process items in batch",
                output="ProcessedData",
                branch_pipe_code="process_item",
                input_list_name="items",
                input_item_name="current_item",
            ),
        },
    ),
)

# Export all PipeBatch test cases
PIPE_BATCH_TEST_CASES = [
    PIPE_BATCH,
]
