from typing import ClassVar

from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class SubPipeTestCases:
    SIMPLE_SUB_PIPE = (
        "simple_sub_pipe",
        SubPipeSpec(pipe_code="process_data", result="processed_data"),
        SubPipeBlueprint(pipe="process_data", result="processed_data"),
    )

    SUB_PIPE_WITH_MULTIPLE_OUTPUT = (
        "sub_pipe_with_multiple_output",
        SubPipeSpec(pipe_code="generate_items", result="items", multiple_output=True),
        SubPipeBlueprint(pipe="generate_items", result="items", multiple_output=True),
    )

    SUB_PIPE_WITH_FIXED_OUTPUT = (
        "sub_pipe_with_fixed_output",
        SubPipeSpec(pipe_code="generate_ideas", result="ideas", nb_output=3),
        SubPipeBlueprint(pipe="generate_ideas", result="ideas", nb_output=3),
    )

    SUB_PIPE_WITH_BATCH = (
        "sub_pipe_with_batch",
        SubPipeSpec(pipe_code="process_item", result="processed_items", batch_over="input_list", batch_as="current_item"),
        SubPipeBlueprint(pipe="process_item", result="processed_items", batch_over="input_list", batch_as="current_item"),
    )

    TEST_CASES: ClassVar[list[tuple[str, SubPipeSpec, SubPipeBlueprint]]] = [
        SIMPLE_SUB_PIPE,
        SUB_PIPE_WITH_MULTIPLE_OUTPUT,
        SUB_PIPE_WITH_FIXED_OUTPUT,
        SUB_PIPE_WITH_BATCH,
    ]
