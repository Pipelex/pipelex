from pipelex.core.pipes.pipe_input_spec import InputRequirementBlueprint
from pipelex.pipe_controllers.pipe_sequence_factory import PipeSequenceBlueprint, PipeSequenceFactory
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint


class TestPipeSequenceValidation:
    """Tests for PipeSequence validate_inputs method"""

    def test_pipe_sequence_creation(self):
        """Test basic PipeSequence creation"""
        pipe_sequence_blueprint = PipeSequenceBlueprint(
            definition="Test sequence for validation",
            inputs={"text": InputRequirementBlueprint(concept_code="test_domain.Text")},
            output="test_domain.ProcessedText",
            steps=[SubPipeBlueprint(pipe="test_pipe_1", result="intermediate_result")],
        )

        pipe_sequence = PipeSequenceFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code="test_sequence",
            pipe_blueprint=pipe_sequence_blueprint,
        )

        assert pipe_sequence.code == "test_sequence"
        assert pipe_sequence.domain == "test_domain"
        assert len(pipe_sequence.sequential_sub_pipes) == 1
        assert pipe_sequence.sequential_sub_pipes[0].pipe_code == "test_pipe_1"
        assert pipe_sequence.sequential_sub_pipes[0].output_name == "intermediate_result"

    def test_pipe_sequence_multiple_sub_pipes(self):
        """Test PipeSequence with multiple sequential sub-pipes"""
        pipe_sequence_blueprint = PipeSequenceBlueprint(
            definition="Test sequence with multiple steps",
            inputs={"initial_input": InputRequirementBlueprint(concept_code="test_domain.Text")},
            output="test_domain.FinalOutput",
            steps=[SubPipeBlueprint(pipe="step_1", result="intermediate"), SubPipeBlueprint(pipe="step_2", result="final_output")],
        )

        pipe_sequence = PipeSequenceFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code="test_sequence",
            pipe_blueprint=pipe_sequence_blueprint,
        )

        assert pipe_sequence.code == "test_sequence"
        assert len(pipe_sequence.sequential_sub_pipes) == 2
        assert pipe_sequence.inputs.root["initial_input"].concept.code == "test_domain.Text"
