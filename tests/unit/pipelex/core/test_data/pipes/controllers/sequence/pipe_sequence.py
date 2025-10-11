from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint

PIPE_SEQUENCE = (
    "pipe_sequence",
    """domain = "test_pipes"
description = "Domain with sequence pipe"

[pipe.process_sequence]
type = "PipeSequence"
description = "Process data in sequence"
output = "ProcessedData"
steps = [
    { pipe = "step1", result = "intermediate1" },
    { pipe = "step2", result = "final_result" },
]
""",
    PipelexBundleBlueprint(
        domain="test_pipes",
        description="Domain with sequence pipe",
        pipe={
            "process_sequence": PipeSequenceBlueprint(
                type="PipeSequence",
                description="Process data in sequence",
                output="ProcessedData",
                steps=[
                    SubPipeBlueprint(pipe="step1", result="intermediate1"),
                    SubPipeBlueprint(pipe="step2", result="final_result"),
                ],
            ),
        },
    ),
)

# Export all PipeSequence test cases
PIPE_SEQUENCE_TEST_CASES = [
    PIPE_SEQUENCE,
]
