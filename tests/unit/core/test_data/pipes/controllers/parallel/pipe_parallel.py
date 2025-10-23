from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint

PIPE_PARALLEL = (
    "pipe_parallel",
    """domain = "test_pipes"
description = "Domain with parallel pipe"

[pipe.parallel_process]
type = "PipeParallel"
description = "PipeParallel example in PIPE_PARALLEL_TEST_CASES"
output = "ProcessedData"
parallels = [
    { pipe = "process_a", result = "result_a" },
    { pipe = "process_b", result = "result_b" },
]
add_each_output = true
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with parallel pipe",
        pipe={
            "parallel_process": PipeParallelBlueprint(
                type="PipeParallel",
                description="PipeParallel example in PIPE_PARALLEL_TEST_CASES",
                output="ProcessedData",
                parallels=[
                    SubPipeBlueprint(pipe="process_a", result="result_a"),
                    SubPipeBlueprint(pipe="process_b", result="result_b"),
                ],
                add_each_output=True,
            ),
        },
    ),
)

# Export all PipeParallel test cases
PIPE_PARALLEL_TEST_CASES = [
    PIPE_PARALLEL,
]
