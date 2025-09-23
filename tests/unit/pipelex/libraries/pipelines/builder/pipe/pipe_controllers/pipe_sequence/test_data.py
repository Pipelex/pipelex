"""
Test data for PipeSequenceBlueprint conversion tests.
"""

from typing import ClassVar, List, Tuple

from pipelex.core.pipes.pipe_input_spec_blueprint import (
    InputRequirementBlueprint as InputRequirementBlueprintCore,
)
from pipelex.libraries.pipelines.builder.pipe.inputs import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_sequence_builder import PipeSequenceBlueprint
from pipelex.libraries.pipelines.builder.pipe.sub_pipe_builder import SubPipeBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import (
    PipeSequenceBlueprint as PipeSequenceBlueprintCore,
)
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint as SubPipeBlueprintCore


class PipeSequenceTestCases:
    """Test cases for PipeSequenceBlueprint conversion."""

    SIMPLE_SEQUENCE = (
        "simple_sequence",
        PipeSequenceBlueprint(
            definition="A sequence of operations",
            inputs={"input_data": InputRequirementBlueprint(concept="Text")},
            output="ProcessedData",
            steps=[
                SubPipeBlueprint(pipe="step1", result="result1"),
                SubPipeBlueprint(pipe="step2", result="result2"),
                SubPipeBlueprint(pipe="step3", result="final_result"),
            ],
        ),
        "sequence_pipe",
        "test_domain",
        PipeSequenceBlueprintCore(
            definition="A sequence of operations",
            inputs={"input_data": InputRequirementBlueprintCore(concept="Text")},
            output="ProcessedData",
            type="PipeSequence",
            category="PipeController",
            steps=[
                SubPipeBlueprintCore(pipe="step1", result="result1"),
                SubPipeBlueprintCore(pipe="step2", result="result2"),
                SubPipeBlueprintCore(pipe="step3", result="final_result"),
            ],
        ),
    )

    SEQUENCE_WITH_BATCH = (
        "sequence_with_batch",
        PipeSequenceBlueprint(
            definition="Sequence with batch",
            inputs={"items": InputRequirementBlueprint(concept="ItemList")},
            output="ProcessedItems",
            steps=[
                SubPipeBlueprint(pipe="prepare", result="prepared_items"),
                SubPipeBlueprint(
                    pipe="process_item",
                    result="processed_items",
                    batch_over="prepared_items",
                    batch_as="current_item",
                ),
            ],
        ),
        "batch_sequence",
        "test_domain",
        PipeSequenceBlueprintCore(
            definition="Sequence with batch",
            inputs={"items": InputRequirementBlueprintCore(concept="ItemList")},
            output="ProcessedItems",
            type="PipeSequence",
            category="PipeController",
            steps=[
                SubPipeBlueprintCore(pipe="prepare", result="prepared_items"),
                SubPipeBlueprintCore(
                    pipe="process_item",
                    result="processed_items",
                    batch_over="prepared_items",
                    batch_as="current_item",
                ),
            ],
        ),
    )

    TEST_CASES: ClassVar[List[Tuple[str, PipeSequenceBlueprint, str, str, PipeSequenceBlueprintCore]]] = [
        SIMPLE_SEQUENCE,
        SEQUENCE_WITH_BATCH,
    ]
