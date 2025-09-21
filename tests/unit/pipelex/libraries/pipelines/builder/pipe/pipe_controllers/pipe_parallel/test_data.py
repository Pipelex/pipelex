"""
Test data for PipeParallelBlueprint conversion tests.
"""

from typing import ClassVar, List, Tuple

from pipelex.core.pipes.pipe_input_spec_blueprint import (
    InputRequirementBlueprint as InputRequirementBlueprintCore,
)
from pipelex.libraries.pipelines.builder.pipe.inputs import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_parallel import PipeParallelBlueprint
from pipelex.libraries.pipelines.builder.pipe.sub_pipe import SubPipeBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import (
    PipeParallelBlueprint as PipeParallelBlueprintCore,
)
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint as SubPipeBlueprintCore


class PipeParallelTestCases:
    """Test cases for PipeParallelBlueprint conversion."""

    SIMPLE_PARALLEL = (
        "simple_parallel",
        PipeParallelBlueprint(
            definition="Run pipes in parallel",
            inputs={"data": InputRequirementBlueprint(concept="Data")},
            output="Results",
            parallels=[
                SubPipeBlueprint(pipe="analyze_data", result="analysis"),
                SubPipeBlueprint(pipe="transform_data", result="transformed"),
                SubPipeBlueprint(pipe="validate_data", result="validation"),
            ],
        ),
        "parallel_processor",
        "test_domain",
        PipeParallelBlueprintCore(
            definition="Run pipes in parallel",
            inputs={"data": InputRequirementBlueprintCore(concept="Data")},
            output="Results",
            type="PipeParallel",
            category="PipeController",
            parallels=[
                SubPipeBlueprintCore(pipe="analyze_data", result="analysis"),
                SubPipeBlueprintCore(pipe="transform_data", result="transformed"),
                SubPipeBlueprintCore(pipe="validate_data", result="validation"),
            ],
            add_each_output=True,
            combined_output=None,
        ),
    )

    PARALLEL_WITH_COMBINED = (
        "parallel_with_combined",
        PipeParallelBlueprint(
            definition="Parallel with combined output",
            inputs={"input": InputRequirementBlueprint(concept="Input")},
            output="CombinedResult",
            parallels=[
                SubPipeBlueprint(pipe="pipe1", result="result1"),
                SubPipeBlueprint(pipe="pipe2", result="result2"),
            ],
            add_each_output=False,
            combined_output="MergedData",
        ),
        "combined_parallel",
        "test_domain",
        PipeParallelBlueprintCore(
            definition="Parallel with combined output",
            inputs={"input": InputRequirementBlueprintCore(concept="Input")},
            output="CombinedResult",
            type="PipeParallel",
            category="PipeController",
            parallels=[
                SubPipeBlueprintCore(pipe="pipe1", result="result1"),
                SubPipeBlueprintCore(pipe="pipe2", result="result2"),
            ],
            add_each_output=False,
            combined_output="MergedData",
        ),
    )

    TEST_CASES: ClassVar[List[Tuple[str, PipeParallelBlueprint, str, str, PipeParallelBlueprintCore]]] = [
        SIMPLE_PARALLEL,
        PARALLEL_WITH_COMBINED,
    ]
