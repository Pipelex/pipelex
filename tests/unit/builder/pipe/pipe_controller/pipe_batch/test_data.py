from typing import ClassVar

from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint


class PipeBatchTestCases:
    BATCH_WITH_NAMES = (
        "batch_with_names",
        PipeBatchSpec(
            pipe_code="named_batch",
            description="Batch with custom names",
            inputs={"data": "DataList"},
            output="Results",
            branch_pipe_code="transform_data",
            input_list_name="data_list",
            input_item_name="current_data",
        ),
        PipeBatchBlueprint(
            description="Batch with custom names",
            inputs={"data": "DataList"},
            output="Results",
            type="PipeBatch",
            pipe_category="PipeController",
            branch_pipe_code="transform_data",
            input_list_name="data_list",
            input_item_name="current_data",
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeBatchSpec, PipeBatchBlueprint]]] = [
        BATCH_WITH_NAMES,
    ]
