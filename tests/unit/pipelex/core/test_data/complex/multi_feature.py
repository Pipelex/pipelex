from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint

COMPLEX_PIPES = (
    "complex_pipes",
    """domain = "complex_domain"
description = "Domain with multiple pipe types"

[concept]
InputData = "Input data concept"
ProcessedData = "Processed data concept"

[pipe.llm_pipe]
type = "PipeLLM"
description = "Generate content"
inputs = { data = "InputData" }
output = "ProcessedData"
prompt_template = "Process this data: @data"

[pipe.sequence_pipe]
type = "PipeSequence"
description = "Sequential processing"
inputs = { input_data = "InputData" }
output = "ProcessedData"
steps = [
    { pipe = "llm_pipe", result = "llm_result" },
    { pipe = "final_step", result = "final_output" },
]
""",
    PipelexBundleBlueprint(
        domain="complex_domain",
        description="Domain with multiple pipe types",
        concept={
            "InputData": "Input data concept",
            "ProcessedData": "Processed data concept",
        },
        pipe={
            "llm_pipe": PipeLLMBlueprint(
                type="PipeLLM",
                description="Generate content",
                inputs={"data": "InputData"},
                output="ProcessedData",
                prompt_template="Process this data: @data",
            ),
            "sequence_pipe": PipeSequenceBlueprint(
                type="PipeSequence",
                description="Sequential processing",
                inputs={"input_data": "InputData"},
                output="ProcessedData",
                steps=[
                    SubPipeBlueprint(pipe="llm_pipe", result="llm_result"),
                    SubPipeBlueprint(pipe="final_step", result="final_output"),
                ],
            ),
        },
    ),
)

# Export all complex test cases
COMPLEX_TEST_CASES = [
    COMPLEX_PIPES,
]
