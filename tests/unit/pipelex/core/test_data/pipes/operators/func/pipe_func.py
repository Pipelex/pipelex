from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint

PIPE_FUNC = (
    "pipe_func",
    """domain = "test_pipes"
definition = "Domain with function pipe"

[pipe.process_data]
type = "PipeFunc"
definition = "Process data with function"
output = "ProcessedData"
function_name = "process_data_function"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with function pipe",
        pipe={
            "process_data": PipeFuncBlueprint(
                type="PipeFunc",
                definition="Process data with function",
                output="ProcessedData",
                function_name="process_data_function",
            ),
        },
    ),
)

# Export all PipeFunc test cases
PIPE_FUNC_TEST_CASES = [
    PIPE_FUNC,
]
