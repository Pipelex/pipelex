from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint

PIPE_SEQUENCE = (
    "pipe_sequence",
    """domain = "test_pipes"
description = "Domain with sequence pipe"

[concept]
ProcessedData = "Processed data concept"

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
        concept={"ProcessedData": "Processed data concept"},
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

PIPE_SEQUENCE_WITH_CROSS_DOMAIN_REF = (
    "pipe_sequence_with_cross_domain_ref",
    """domain = "orchestration"
description = "Domain with cross-domain pipe ref in sequence"

[pipe.orchestrate]
type = "PipeSequence"
description = "Orchestrate with cross-domain pipe"
output = "Text"
steps = [
    { pipe = "scoring.compute_score", result = "score" },
    { pipe = "format_result", result = "final" },
]
""",
    PipelexBundleBlueprint(
        domain="orchestration",
        description="Domain with cross-domain pipe ref in sequence",
        pipe={
            "orchestrate": PipeSequenceBlueprint(
                type="PipeSequence",
                description="Orchestrate with cross-domain pipe",
                output="Text",
                steps=[
                    SubPipeBlueprint(pipe="scoring.compute_score", result="score"),
                    SubPipeBlueprint(pipe="format_result", result="final"),
                ],
            ),
        },
    ),
)

# Export all PipeSequence test cases
PIPE_SEQUENCE_TEST_CASES = [
    PIPE_SEQUENCE,
    PIPE_SEQUENCE_WITH_CROSS_DOMAIN_REF,
]
