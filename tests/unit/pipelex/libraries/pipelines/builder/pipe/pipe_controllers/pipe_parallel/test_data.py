from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.inputs_spec import InputRequirementSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.libraries.pipelines.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class PipeParallelTestCases:
    SIMPLE_PARALLEL = (
        "simple_parallel",
        PipeParallelSpec(
            the_pipe_code="parallel_processor",
            definition="Run pipes in parallel",
            inputs={"data": InputRequirementSpec(concept="Data")},
            output="Results",
            parallels=[
                SubPipeSpec(the_pipe_code="analyze_data", result="analysis"),
                SubPipeSpec(the_pipe_code="transform_data", result="transformed"),
                SubPipeSpec(the_pipe_code="validate_data", result="validation"),
            ],
        ),
        PipeParallelBlueprint(
            definition="Run pipes in parallel",
            inputs={"data": InputRequirementBlueprint(concept="Data")},
            output="Results",
            type="PipeParallel",
            category="PipeController",
            parallels=[
                SubPipeBlueprint(pipe="analyze_data", result="analysis"),
                SubPipeBlueprint(pipe="transform_data", result="transformed"),
                SubPipeBlueprint(pipe="validate_data", result="validation"),
            ],
            add_each_output=True,
            combined_output=None,
        ),
    )

    PARALLEL_WITH_COMBINED = (
        "parallel_with_combined",
        PipeParallelSpec(
            the_pipe_code="combined_parallel",
            definition="Parallel with combined output",
            inputs={"input": InputRequirementSpec(concept="Input")},
            output="CombinedResult",
            parallels=[
                SubPipeSpec(the_pipe_code="pipe1", result="result1"),
                SubPipeSpec(the_pipe_code="pipe2", result="result2"),
            ],
            add_each_output=False,
            combined_output="MergedData",
        ),
        PipeParallelBlueprint(
            definition="Parallel with combined output",
            inputs={"input": InputRequirementBlueprint(concept="Input")},
            output="CombinedResult",
            type="PipeParallel",
            category="PipeController",
            parallels=[
                SubPipeBlueprint(pipe="pipe1", result="result1"),
                SubPipeBlueprint(pipe="pipe2", result="result2"),
            ],
            add_each_output=False,
            combined_output="MergedData",
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeParallelSpec, PipeParallelBlueprint]]] = [
        SIMPLE_PARALLEL,
        PARALLEL_WITH_COMBINED,
    ]
