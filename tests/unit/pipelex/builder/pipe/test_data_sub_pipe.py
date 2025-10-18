from typing import ClassVar

from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class SubPipeTestCases:
    SIMPLE_SUB_PIPE = (
        "simple_sub_pipe",
        SubPipeSpec(pipe_code="process_data", result="processed_data"),
        SubPipeBlueprint(pipe="process_data", result="processed_data"),
    )

    SUB_PIPE_WITH_BATCH = (
        "sub_pipe_with_batch",
        SubPipeSpec(pipe_code="process_item", result="processed_items", batch_over="input_list", batch_as="current_item"),
        SubPipeBlueprint(pipe="process_item", result="processed_items", batch_over="input_list", batch_as="current_item"),
    )

    TEST_CASES: ClassVar[list[tuple[str, SubPipeSpec, SubPipeBlueprint]]] = [
        SIMPLE_SUB_PIPE,
        SUB_PIPE_WITH_BATCH,
    ]
