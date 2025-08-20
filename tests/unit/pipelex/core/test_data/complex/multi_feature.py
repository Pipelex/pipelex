"""Complex test cases combining multiple features."""

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.pipes.pipe_input_spec import InputRequirementBlueprint
from pipelex.pipe_controllers.pipe_sequence_factory import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint
from pipelex.pipe_operators.pipe_llm_factory import PipeLLMBlueprint

COMPLEX_PIPES = (
    "complex_pipes",
    """domain = "complex_domain"
definition = "Domain with multiple pipe types"

[concept]
InputData = "Input data concept"
ProcessedData = "Processed data concept"

[pipe.llm_pipe]
type = "PipeLLM"
definition = "Generate content"
output = "ProcessedData"
inputs = { data = "InputData" }
prompt_template = "Process this data: @data"

[pipe.sequence_pipe]
type = "PipeSequence"
definition = "Sequential processing"
output = "ProcessedData"
inputs = { input_data = "InputData" }
steps = [
    { pipe = "llm_pipe", result = "llm_result" },
    { pipe = "final_step", result = "final_output" },
]
""",
    PipelexBundleBlueprint(
        domain="complex_domain",
        definition="Domain with multiple pipe types",
        concept={
            "InputData": "Input data concept",
            "ProcessedData": "Processed data concept",
        },
        pipe={
            "llm_pipe": PipeLLMBlueprint(
                type="PipeLLM",
                definition="Generate content",
                inputs={"data": InputRequirementBlueprint(concept_code="InputData")},
                output="ProcessedData",
                prompt_template="Process this data: @data",
            ),
            "sequence_pipe": PipeSequenceBlueprint(
                type="PipeSequence",
                definition="Sequential processing",
                inputs={"input_data": InputRequirementBlueprint(concept_code="InputData")},
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
