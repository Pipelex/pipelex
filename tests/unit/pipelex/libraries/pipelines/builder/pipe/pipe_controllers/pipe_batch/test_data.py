"""
Test data for PipeBatchBlueprint conversion tests.
"""

from typing import ClassVar, List, Tuple

from pipelex.core.pipes.pipe_input_spec_blueprint import (
    InputRequirementBlueprint as InputRequirementBlueprintCore,
)
from pipelex.libraries.pipelines.builder.pipe.inputs import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_batch_builder import PipeBatchBlueprint
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint as PipeBatchBlueprintCore


class PipeBatchTestCases:
    """Test cases for PipeBatchBlueprint conversion."""

    SIMPLE_BATCH = (
        "simple_batch",
        PipeBatchBlueprint(
            definition="Process items in batch",
            inputs={"items": InputRequirementBlueprint(concept="ItemList")},
            output="ProcessedItems",
            branch_pipe_code="process_item",
        ),
        "batch_processor",
        "test_domain",
        PipeBatchBlueprintCore(
            definition="Process items in batch",
            inputs={"items": InputRequirementBlueprintCore(concept="ItemList")},
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
        PipeBatchBlueprint(
            definition="Batch with custom names",
            inputs={"data": InputRequirementBlueprint(concept="DataList")},
            output="Results",
            branch_pipe_code="transform_data",
            input_list_name="data_list",
            input_item_name="current_data",
        ),
        "named_batch",
        "test_domain",
        PipeBatchBlueprintCore(
            definition="Batch with custom names",
            inputs={"data": InputRequirementBlueprintCore(concept="DataList")},
            output="Results",
            type="PipeBatch",
            category="PipeController",
            branch_pipe_code="transform_data",
            input_list_name="data_list",
            input_item_name="current_data",
        ),
    )

    TEST_CASES: ClassVar[List[Tuple[str, PipeBatchBlueprint, str, str, PipeBatchBlueprintCore]]] = [
        SIMPLE_BATCH,
        BATCH_WITH_NAMES,
    ]
