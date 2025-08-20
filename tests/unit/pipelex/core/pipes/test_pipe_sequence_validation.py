from pipelex.core.pipes.pipe_input_spec import InputRequirementBlueprint, PipeInputSpec
from pipelex.pipe_controllers.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sub_pipe import SubPipe


class TestPipeSequenceValidation:
    """Tests for PipeSequence validate_inputs method"""

    def test_pipe_sequence_creation(self):
        """Test basic PipeSequence creation"""
        pipe_sequence = PipeSequence(
            domain="test_domain",
            code="test_sequence",
            inputs=PipeInputSpec.make_from_blueprint(
                domain="test_domain", blueprint={"text": InputRequirementBlueprint(concept_code="test_domain.Text")}
            ),
            output_concept_code="test_domain.ProcessedText",
            sequential_sub_pipes=[SubPipe(pipe_code="test_pipe_1", output_name="intermediate_result")],
        )

        assert pipe_sequence.code == "test_sequence"
        assert pipe_sequence.domain == "test_domain"
        assert len(pipe_sequence.sequential_sub_pipes) == 1
        assert pipe_sequence.sequential_sub_pipes[0].pipe_code == "test_pipe_1"
        assert pipe_sequence.sequential_sub_pipes[0].output_name == "intermediate_result"

    def test_pipe_sequence_multiple_sub_pipes(self):
        """Test PipeSequence with multiple sequential sub-pipes"""
        pipe_sequence = PipeSequence(
            domain="test_domain",
            code="test_sequence",
            inputs=PipeInputSpec.make_from_blueprint(
                domain="test_domain", blueprint={"initial_input": InputRequirementBlueprint(concept_code="test_domain.Text")}
            ),
            output_concept_code="test_domain.FinalOutput",
            sequential_sub_pipes=[SubPipe(pipe_code="step_1", output_name="intermediate"), SubPipe(pipe_code="step_2", output_name="final_output")],
        )

        assert pipe_sequence.code == "test_sequence"
        assert len(pipe_sequence.sequential_sub_pipes) == 2
        assert pipe_sequence.inputs.root["initial_input"].concept_code == "test_domain.Text"
