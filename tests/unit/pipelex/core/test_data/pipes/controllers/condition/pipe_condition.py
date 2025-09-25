from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint, PipeConditionPipeMapBlueprint

PIPE_CONDITION = (
    "pipe_condition",
    """domain = "test_pipes"
definition = "Domain with conditional pipe"

[pipe.conditional_process]
type = "PipeCondition"
definition = "Process based on condition"
output = "ProcessedData"
pipe_map = { small = "process_small", large = "process_large" }
expression = "input_data.category"
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        definition="Domain with conditional pipe",
        pipe={
            "conditional_process": PipeConditionBlueprint(
                type="PipeCondition",
                definition="Process based on condition",
                output="ProcessedData",
                expression="input_data.category",
                pipe_map=PipeConditionPipeMapBlueprint(
                    {
                        "small": "process_small",
                        "large": "process_large",
                    },
                ),
            ),
        },
    ),
)

# Export all PipeCondition test cases
PIPE_CONDITION_TEST_CASES = [
    PIPE_CONDITION,
]
