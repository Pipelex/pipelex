"""
Test data for SubPipeBlueprint conversion tests.
"""

from typing import ClassVar, List, Tuple

from pipelex.libraries.pipelines.builder.pipe.sub_pipe_builder import SubPipeBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint as SubPipeBlueprintCore


class SubPipeTestCases:
    """Test cases for SubPipeBlueprint conversion."""

    SIMPLE_SUB_PIPE = (
        "simple_sub_pipe",
        SubPipeBlueprint(pipe="process_data", result="processed_data"),
        SubPipeBlueprintCore(pipe="process_data", result="processed_data"),
    )

    SUB_PIPE_WITH_MULTIPLE_OUTPUT = (
        "sub_pipe_with_multiple_output",
        SubPipeBlueprint(pipe="generate_items", result="items", multiple_output=True),
        SubPipeBlueprintCore(pipe="generate_items", result="items", multiple_output=True),
    )

    SUB_PIPE_WITH_FIXED_OUTPUT = (
        "sub_pipe_with_fixed_output",
        SubPipeBlueprint(pipe="generate_ideas", result="ideas", nb_output=3),
        SubPipeBlueprintCore(pipe="generate_ideas", result="ideas", nb_output=3),
    )

    SUB_PIPE_WITH_BATCH = (
        "sub_pipe_with_batch",
        SubPipeBlueprint(pipe="process_item", result="processed_items", batch_over="input_list", batch_as="current_item"),
        SubPipeBlueprintCore(pipe="process_item", result="processed_items", batch_over="input_list", batch_as="current_item"),
    )

    TEST_CASES: ClassVar[List[Tuple[str, SubPipeBlueprint, SubPipeBlueprintCore]]] = [
        SIMPLE_SUB_PIPE,
        SUB_PIPE_WITH_MULTIPLE_OUTPUT,
        SUB_PIPE_WITH_FIXED_OUTPUT,
        SUB_PIPE_WITH_BATCH,
    ]
