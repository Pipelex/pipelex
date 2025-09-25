from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint

PIPE_PARALLEL = (
    "pipe_parallel",
    """domain = "test_pipes"
definition = "Domain with parallel pipe"

[pipe.parallel_process]
type = "PipeParallel"
definition = "Process data in parallel"
output = "ProcessedData"
parallels = [
    { pipe = "process_a", result = "result_a" },
    { pipe = "process_b", result = "result_b" },
]
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with parallel pipe",
        pipe={
            "parallel_process": PipeParallelBlueprint(
                type="PipeParallel",
                definition="Process data in parallel",
                output="ProcessedData",
                parallels=[
                    SubPipeBlueprint(pipe="process_a", result="result_a"),
                    SubPipeBlueprint(pipe="process_b", result="result_b"),
                ],
            ),
        },
    ),
)

# Export all PipeParallel test cases
PIPE_PARALLEL_TEST_CASES = [
    PIPE_PARALLEL,
]
