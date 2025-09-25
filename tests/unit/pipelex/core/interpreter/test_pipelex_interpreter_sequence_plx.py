import pytest

from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class TestPipelexInterpreterSequencePLX:
    @pytest.mark.parametrize(
        "pipe_name,blueprint,expected_plx",
        [
            # Simple sequence pipe with 2 steps
            (
                "simple_sequence",
                PipeSequenceBlueprint(
                    type="PipeSequence",
                    definition="Process data in sequence",
                    output="ProcessedData",
                    steps=[
                        SubPipeBlueprint(pipe="extract_info", result="extracted"),
                        SubPipeBlueprint(pipe="summarize", result="final_summary"),
                    ],
                ),
                """[pipe.simple_sequence]
type = "PipeSequence"
definition = "Process data in sequence"
output = "ProcessedData"
steps = [
    { pipe = "extract_info", result = "extracted" },
    { pipe = "summarize", result = "final_summary" },
]""",
            ),
            # Sequence pipe with inputs and steps
            (
                "sequence_with_inputs",
                PipeSequenceBlueprint(
                    type="PipeSequence",
                    definition="Process data with inputs",
                    inputs={"text": InputRequirementBlueprint(concept="Text", multiplicity=1), "topic": "Text"},
                    output="ProcessedData",
                    steps=[
                        SubPipeBlueprint(pipe="extract_info", result="extracted"),
                        SubPipeBlueprint(pipe="summarize", result="final_summary"),
                    ],
                ),
                """[pipe.sequence_with_inputs]
type = "PipeSequence"
definition = "Process data with inputs"
inputs = { text = { concept = "Text", multiplicity = 1 }, topic = "Text" }
output = "ProcessedData"
steps = [
    { pipe = "extract_info", result = "extracted" },
    { pipe = "summarize", result = "final_summary" },
]""",
            ),
            # Sequence pipe with complex sub pipe options
            (
                "complex_sequence",
                PipeSequenceBlueprint(
                    type="PipeSequence",
                    definition="Complex sequence processing",
                    output="ProcessedData",
                    steps=[
                        SubPipeBlueprint(pipe="step1", result="result1", nb_output=2),
                        SubPipeBlueprint(pipe="step2", result="result2", multiple_output=True),
                        SubPipeBlueprint(pipe="step3", result="result3", batch_over="items", batch_as="item"),
                    ],
                ),
                """[pipe.complex_sequence]
type = "PipeSequence"
definition = "Complex sequence processing"
output = "ProcessedData"
steps = [
    { pipe = "step1", result = "result1", nb_output = 2 },
    { pipe = "step2", result = "result2", multiple_output = true },
    { pipe = "step3", result = "result3", batch_over = "items", batch_as = "item" },
]""",
            ),
        ],
    )
    def test_sequence_pipe_to_plx_string(self, pipe_name: str, blueprint: PipeSequenceBlueprint, expected_plx: str):
        result = PipelexInterpreter.sequence_pipe_to_plx_string(pipe_name, blueprint)
        assert result == expected_plx
