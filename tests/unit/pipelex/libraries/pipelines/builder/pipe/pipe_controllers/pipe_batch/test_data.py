from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint


class PipeBatchTestCases:
    SIMPLE_BATCH = (
        "simple_batch",
        PipeBatchSpec(
            the_pipe_code="batch_processor",
            definition="Process items in batch",
            inputs={"items": "ItemList"},
            output="ProcessedItems",
            branch_pipe_code="process_item",
        ),
        PipeBatchBlueprint(
            definition="Process items in batch",
            inputs={"items": InputRequirementBlueprint(concept="ItemList")},
            output="ProcessedItems",
            type="PipeBatch",
            category="PipeController",
            branch_pipe_code="process_item",
            input_list_name=None,
            input_item_name=None,
        ),
    )

    BATCH_WITH_NAMES = (
        "batch_with_names",
        PipeBatchSpec(
            the_pipe_code="named_batch",
            definition="Batch with custom names",
            inputs={"data": "DataList"},
            output="Results",
            branch_pipe_code="transform_data",
            input_list_name="data_list",
            input_item_name="current_data",
        ),
        PipeBatchBlueprint(
            definition="Batch with custom names",
            inputs={"data": InputRequirementBlueprint(concept="DataList")},
            output="Results",
            type="PipeBatch",
            category="PipeController",
            branch_pipe_code="transform_data",
            input_list_name="data_list",
            input_item_name="current_data",
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeBatchSpec, PipeBatchBlueprint]]] = [
        SIMPLE_BATCH,
        BATCH_WITH_NAMES,
    ]
