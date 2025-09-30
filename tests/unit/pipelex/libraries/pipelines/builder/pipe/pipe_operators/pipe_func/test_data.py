from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint

from pipelex.libraries.pipelines.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint


class PipeFuncTestCases:
    SIMPLE_FUNC = (
        "simple_func",
        PipeFuncSpec(
            the_pipe_code="func_processor",
            definition="Execute a function",
            inputs={"data": "Data"},
            output="ProcessedData",
            function_name="process_data",
        ),
        PipeFuncBlueprint(
            definition="Execute a function",
            inputs={"data": InputRequirementBlueprint(concept="Data")},
            output="ProcessedData",
            type="PipeFunc",
            category="PipeOperator",
            function_name="process_data",
        ),
    )

    FUNC_NO_INPUTS = (
        "func_no_inputs",
        PipeFuncSpec(
            the_pipe_code="generator_func",
            definition="Generate data",
            inputs={},
            output="GeneratedData",
            function_name="generate_data",
        ),
        PipeFuncBlueprint(
            definition="Generate data",
            inputs=None,
            output="GeneratedData",
            type="PipeFunc",
            category="PipeOperator",
            function_name="generate_data",
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeFuncSpec, PipeFuncBlueprint]]] = [
        SIMPLE_FUNC,
        FUNC_NO_INPUTS,
    ]
