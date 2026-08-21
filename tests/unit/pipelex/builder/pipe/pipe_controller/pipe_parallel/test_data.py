from typing import ClassVar

from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec
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
            branches=[
                SubPipeSpec(pipe_code="analyze_data", result="analysis"),
                SubPipeSpec(pipe_code="transform_data", result="transformed"),
                SubPipeSpec(pipe_code="validate_data", result="validation"),
            ],
            add_each_output=True,
        ),
        PipeParallelBlueprint(
            description="Run pipes in parallel",
            inputs={"data": "Data"},
            output="Results",
            branches=[
                SubPipeBlueprint(pipe="analyze_data", result="analysis"),
                SubPipeBlueprint(pipe="transform_data", result="transformed"),
                SubPipeBlueprint(pipe="validate_data", result="validation"),
            ],
            add_each_output=True,
            source="tests/unit/pipelex/libraries/pipelines/builder/pipe/pipe_controllers/pipe_parallel/test_data.py PipeParallelTestCases.PARALLEL_WITH_EACH_OUTPUT",  # ruff: ignore[line-too-long]
        ),
    )

    PARALLEL_WITHOUT_EACH_OUTPUT = (
        "parallel_without_each_output",
        PipeParallelSpec(
            pipe_code="combined_parallel",
            description="Parallel combining into its declared output only",
            inputs={"input": "Input"},
            output="CombinedResult",
            branches=[
                SubPipeSpec(pipe_code="pipe1", result="result1"),
                SubPipeSpec(pipe_code="pipe2", result="result2"),
            ],
            add_each_output=False,
        ),
        PipeParallelBlueprint(
            description="Parallel combining into its declared output only",
            inputs={"input": "Input"},
            output="CombinedResult",
            branches=[
                SubPipeBlueprint(pipe="pipe1", result="result1"),
                SubPipeBlueprint(pipe="pipe2", result="result2"),
            ],
            add_each_output=False,
            source="tests/unit/pipelex/libraries/pipelines/builder/pipe/pipe_controllers/pipe_parallel/test_data.py PipeParallelTestCases.PARALLEL_WITHOUT_EACH_OUTPUT",  # ruff: ignore[line-too-long]
        ),
    )

    PARALLEL_OMITTING_ADD_EACH_OUTPUT = (
        "parallel_omitting_add_each_output",
        PipeParallelSpec(
            pipe_code="plain_combined_parallel",
            description="Always-combine parallel omitting add_each_output entirely",
            inputs={"input": "Input"},
            output="CombinedResult",
            branches=[
                SubPipeSpec(pipe_code="pipe1", result="result1"),
                SubPipeSpec(pipe_code="pipe2", result="result2"),
            ],
        ),
        PipeParallelBlueprint(
            description="Always-combine parallel omitting add_each_output entirely",
            inputs={"input": "Input"},
            output="CombinedResult",
            branches=[
                SubPipeBlueprint(pipe="pipe1", result="result1"),
                SubPipeBlueprint(pipe="pipe2", result="result2"),
            ],
            add_each_output=False,
            source="tests/unit/pipelex/libraries/pipelines/builder/pipe/pipe_controllers/pipe_parallel/test_data.py PipeParallelTestCases.PARALLEL_OMITTING_ADD_EACH_OUTPUT",  # ruff: ignore[line-too-long]
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeParallelSpec, PipeParallelBlueprint]]] = [
        PARALLEL_WITH_EACH_OUTPUT,
        PARALLEL_WITHOUT_EACH_OUTPUT,
        PARALLEL_OMITTING_ADD_EACH_OUTPUT,
    ]
