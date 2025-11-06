from typing import ClassVar

from pipelex.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint


class PipeFuncTestCases:
    SIMPLE_FUNC = (
        "simple_func",
        PipeFuncSpec(
            pipe_code="func_processor",
            description="Execute a function",
            inputs={"data": "Data"},
            output="ProcessedData",
            function_name="process_data",
        ),
        PipeFuncBlueprint(
            description="Execute a function",
            inputs={"data": "Data"},
            output="ProcessedData",
            type="PipeFunc",
            pipe_category="PipeOperator",
            function_name="process_data",
        ),
    )

    FUNC_NO_INPUTS = (
        "func_no_inputs",
        PipeFuncSpec(
            pipe_code="generator_func",
            description="Generate data",
            inputs={},
            output="GeneratedData",
            function_name="generate_data",
        ),
        PipeFuncBlueprint(
            description="Generate data",
            inputs=None,
            output="GeneratedData",
            type="PipeFunc",
            pipe_category="PipeOperator",
            function_name="generate_data",
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeFuncSpec, PipeFuncBlueprint]]] = [
        SIMPLE_FUNC,
        FUNC_NO_INPUTS,
    ]
