from typing import ClassVar

from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint


class PipeBatchTestCases:
    BATCH_WITH_NAMES = (
        "batch_with_names",
        PipeBatchSpec(
            pipe_code="named_batch",
            description="Batch with custom names",
            inputs={"widgets": "Widget[]"},
            output="Results",
            branch_pipe_code="transform_data",
            input_list_name="widgets",
            input_item_name="widget",
        ),
        PipeBatchBlueprint(
            description="Batch with custom names",
            inputs={"widgets": "Widget[]"},
            output="Results",
            branch_pipe_code="transform_data",
            input_list_name="widgets",
            input_item_name="widget",
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeBatchSpec, PipeBatchBlueprint]]] = [
        BATCH_WITH_NAMES,
    ]
