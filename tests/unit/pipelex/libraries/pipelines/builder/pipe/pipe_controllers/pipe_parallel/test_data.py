from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.libraries.pipelines.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class PipeParallelTestCases:
    PARALLEL_WITH_EACH_OUTPUT = (
        "parallel_with_each_output",
        PipeParallelSpec(
            pipe_code="parallel_processor",
            description="Run pipes in parallel",
            inputs={"data": "Data"},
            output="Results",
            parallels=[
                SubPipeSpec(pipe_code="analyze_data", result="analysis"),
                SubPipeSpec(pipe_code="transform_data", result="transformed"),
                SubPipeSpec(pipe_code="validate_data", result="validation"),
            ],
            add_each_output=True,
        ),
        PipeParallelBlueprint(
            description="Run pipes in parallel",
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
            source="tests/unit/pipelex/libraries/pipelines/builder/pipe/pipe_controllers/pipe_parallel/test_data.py PipeParallelTestCases.PARALLEL_WITH_EACH_OUTPUT",  # noqa: E501
        ),
    )

    PARALLEL_WITH_COMBINED = (
        "parallel_with_combined",
        PipeParallelSpec(
            pipe_code="combined_parallel",
            description="Parallel with combined output",
            inputs={"input": "Input"},
            output="CombinedResult",
            parallels=[
                SubPipeSpec(pipe_code="pipe1", result="result1"),
                SubPipeSpec(pipe_code="pipe2", result="result2"),
            ],
            add_each_output=False,
            combined_output="MergedData",
        ),
        PipeParallelBlueprint(
            description="Parallel with combined output",
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
            source="tests/unit/pipelex/libraries/pipelines/builder/pipe/pipe_controllers/pipe_parallel/test_data.py PipeParallelTestCases.PARALLEL_WITH_COMBINED",  # noqa: E501
        ),
    )

    PARALLEL_WITH_BOTH_EACH_OUTPUT_AND_COMBINED = (
        "parallel_with_both_each_output_and_combined",
        PipeParallelSpec(
            pipe_code="combined_parallel",
            description="Parallel with combined output",
            inputs={"input": "Input"},
            output="CombinedResult",
            parallels=[
                SubPipeSpec(pipe_code="pipe1", result="result1"),
                SubPipeSpec(pipe_code="pipe2", result="result2"),
            ],
            add_each_output=True,
            combined_output="MergedData",
        ),
        PipeParallelBlueprint(
            description="Parallel with combined output",
            inputs={"input": InputRequirementBlueprint(concept="Input")},
            output="CombinedResult",
            type="PipeParallel",
            category="PipeController",
            parallels=[
                SubPipeBlueprint(pipe="pipe1", result="result1"),
                SubPipeBlueprint(pipe="pipe2", result="result2"),
            ],
            add_each_output=True,
            combined_output="MergedData",
            source="tests/unit/pipelex/libraries/pipelines/builder/pipe/pipe_controllers/pipe_parallel/test_data.py PipeParallelTestCases.PARALLEL_WITH_BOTH_EACH_OUTPUT_AND_COMBINED",  # noqa: E501
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeParallelSpec, PipeParallelBlueprint]]] = [
        PARALLEL_WITH_EACH_OUTPUT,
        PARALLEL_WITH_COMBINED,
        PARALLEL_WITH_BOTH_EACH_OUTPUT_AND_COMBINED,
    ]
