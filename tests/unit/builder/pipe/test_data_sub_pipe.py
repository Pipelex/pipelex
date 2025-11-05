from typing import ClassVar

from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class SubPipeTestCases:
    SIMPLE_SUB_PIPE = (
        "simple_sub_pipe",
        SubPipeSpec(pipe_code="process_data", result="processed_data"),
        SubPipeBlueprint(pipe="process_data", result="processed_data"),
    )

    TEST_CASES: ClassVar[list[tuple[str, SubPipeSpec, SubPipeBlueprint]]] = [
        SIMPLE_SUB_PIPE,
    ]
