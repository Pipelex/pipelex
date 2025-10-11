from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint

PIPE_CONDITION = (
    "pipe_condition",
    """domain = "test_pipes"
description = "Domain with conditional pipe"

[pipe.conditional_process]
type = "PipeCondition"
description = "Process based on condition"
output = "ProcessedData"
expression = "input_data.category"
pipe_map = { small = "process_small", large = "process_large" }
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with conditional pipe",
        pipe={
            "conditional_process": PipeConditionBlueprint(
                type="PipeCondition",
                description="Process based on condition",
                output="ProcessedData",
                expression="input_data.category",
                pipe_map={
                    "small": "process_small",
                    "large": "process_large",
                },
            ),
        },
    ),
)

# Export all PipeCondition test cases
PIPE_CONDITION_TEST_CASES = [
    PIPE_CONDITION,
]
