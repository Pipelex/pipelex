from pipelex.core.pipes.pipe_input_spec import InputRequirementBlueprint, PipeInputSpec
from pipelex.pipe_controllers.pipe_sequence import PipeSequence, SubPipe
from pipelex.pipe_operators.pipe_llm import PipeLLM
from pipelex.pipe_operators.pipe_llm_prompt import PipeLLMPrompt


class TestPipeSequenceValidation:
    """Tests for PipeSequence validate_inputs method"""

    def test_pipe_sequence_creation(self):
        """Test basic PipeSequence creation"""
        # Create a real PipeLLM pipe
        pipe_llm = PipeLLM(
            domain="test_domain",
            code="test_pipe_1",
            output_concept_code="test_domain.ProcessedText",
            pipe_llm_prompt=PipeLLMPrompt(
                code="test_pipe_1_prompt",
                domain="test_domain",
                user_text="Process this text: @text",
            ),
        )

        pipe_sequence = PipeSequence(
            domain="test_domain",
            code="test_sequence",
            inputs=PipeInputSpec.make_from_blueprint(
                domain="test_domain", blueprint={"text": InputRequirementBlueprint(concept_code="test_domain.Text")}
            ),
            output_concept_code="test_domain.ProcessedText",
            sequential_sub_pipes=[SubPipe(pipe=pipe_llm, output_name="intermediate_result")],
        )

        assert pipe_sequence.code == "test_sequence"
        assert pipe_sequence.domain == "test_domain"
        assert len(pipe_sequence.sequential_sub_pipes) == 1
        assert pipe_sequence.sequential_sub_pipes[0].pipe.code == "test_pipe_1"
        assert pipe_sequence.sequential_sub_pipes[0].output_name == "intermediate_result"

    def test_pipe_sequence_multiple_sub_pipes(self):
        """Test PipeSequence with multiple sequential sub-pipes"""
        # Create first PipeLLM pipe
        pipe_llm_1 = PipeLLM(
            domain="test_domain",
            code="step_1",
            output_concept_code="test_domain.IntermediateResult",
            pipe_llm_prompt=PipeLLMPrompt(
                code="step_1_prompt",
                domain="test_domain",
                user_text="Process initial input: @initial_input",
            ),
        )

        # Create second PipeLLM pipe
        pipe_llm_2 = PipeLLM(
            domain="test_domain",
            code="step_2",
            output_concept_code="test_domain.FinalOutput",
            pipe_llm_prompt=PipeLLMPrompt(
                code="step_2_prompt",
                domain="test_domain",
                user_text="Process intermediate result: @intermediate",
            ),
        )

        pipe_sequence = PipeSequence(
            domain="test_domain",
            code="test_sequence",
            inputs=PipeInputSpec.make_from_blueprint(
                domain="test_domain", blueprint={"initial_input": InputRequirementBlueprint(concept_code="test_domain.Text")}
            ),
            output_concept_code="test_domain.FinalOutput",
            sequential_sub_pipes=[SubPipe(pipe=pipe_llm_1, output_name="intermediate"), SubPipe(pipe=pipe_llm_2, output_name="final_output")],
        )

        assert pipe_sequence.code == "test_sequence"
        assert len(pipe_sequence.sequential_sub_pipes) == 2
        assert pipe_sequence.inputs.root["initial_input"].concept_code == "test_domain.Text"
