"""
Test data for PipeFuncBlueprint conversion tests.
"""

from typing import ClassVar, List, Tuple

from pipelex.core.pipes.pipe_input_spec_blueprint import (
    InputRequirementBlueprint as InputRequirementBlueprintCore,
)
from pipelex.libraries.pipelines.builder.pipe.inputs import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_func_builder import PipeFuncBlueprint
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint as PipeFuncBlueprintCore


class PipeFuncTestCases:
    """Test cases for PipeFuncBlueprint conversion."""

    SIMPLE_FUNC = (
        "simple_func",
        PipeFuncBlueprint(
            definition="Execute a function",
            inputs={"data": InputRequirementBlueprint(concept="Data")},
            output="ProcessedData",
            function_name="process_data",
        ),
        "func_processor",
        "test_domain",
        PipeFuncBlueprintCore(
            definition="Execute a function",
            inputs={"data": InputRequirementBlueprintCore(concept="Data")},
            output="ProcessedData",
            type="PipeFunc",
            category="PipeOperator",
            function_name="process_data",
        ),
    )

    FUNC_NO_INPUTS = (
        "func_no_inputs",
        PipeFuncBlueprint(
            definition="Generate data",
            inputs={},
            output="GeneratedData",
            function_name="generate_data",
        ),
        "generator_func",
        "test_domain",
        PipeFuncBlueprintCore(
            definition="Generate data",
            inputs=None,
            output="GeneratedData",
            type="PipeFunc",
            category="PipeOperator",
            function_name="generate_data",
        ),
    )

    TEST_CASES: ClassVar[List[Tuple[str, PipeFuncBlueprint, str, str, PipeFuncBlueprintCore]]] = [
        SIMPLE_FUNC,
        FUNC_NO_INPUTS,
    ]
