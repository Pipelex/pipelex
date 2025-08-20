from pipelex.core.pipes.pipe_input_spec import InputRequirementBlueprint, PipeInputSpec
from pipelex.pipe_controllers.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_operators.pipe_llm import PipeLLM
from pipelex.pipe_operators.pipe_llm_prompt import PipeLLMPrompt


class TestPipeParallelValidation:
    """Tests for PipeParallel creation and basic structure"""

    def test_pipe_parallel_with_real_pipe_structure(self):
        """Test PipeParallel structure with a real pipe"""
        # Create a real PipeLLM that will infer inputs from the prompt template
        real_pipe = PipeLLM(
            domain="test_domain",
            code="analyze_document",
            # Let PipeLLM infer inputs from prompt template - no explicit inputs
            output_concept_code="test_domain.Analysis",
            pipe_llm_prompt=PipeLLMPrompt(
                code="analyze_document_prompt",
                domain="test_domain",
                user_text="Analyze this document:  \n@context\n@document",
            ),
        )

        # Verify the real pipe was created successfully
        assert real_pipe.code == "analyze_document"
        assert real_pipe.domain == "test_domain"
        assert real_pipe.output_concept_code == "test_domain.Analysis"

        # Create PipeParallel that would reference this pipe
        pipe_parallel = PipeParallel(
            domain="test_domain",
            code="parallel_document_processor",
            inputs=PipeInputSpec.make_from_blueprint(
                domain="test_domain",
                blueprint={
                    "document": InputRequirementBlueprint(concept_code="test_domain.document"),
                    "context": InputRequirementBlueprint(concept_code="test_domain.context"),
                },
            ),
            output_concept_code="test_domain.ProcessedAnalysis",
            parallel_sub_pipes=[SubPipe(pipe_code="analyze_document", output_name="analysis_result")],
            add_each_output=True,
            combined_output=None,
        )

        # Verify the PipeParallel structure is correct
        assert len(pipe_parallel.parallel_sub_pipes) == 1
        assert pipe_parallel.parallel_sub_pipes[0].pipe_code == "analyze_document"
        assert pipe_parallel.parallel_sub_pipes[0].output_name == "analysis_result"

        # Verify PipeParallel has the expected structure
        assert pipe_parallel.domain == "test_domain"
        assert pipe_parallel.code == "parallel_document_processor"
        assert pipe_parallel.add_each_output is True

    def test_pipe_parallel_creation(self):
        """Test basic PipeParallel creation and structure"""
        # Create a simple PipeParallel with proper inputs
        pipe_parallel = PipeParallel(
            domain="test_domain",
            code="test_parallel",
            inputs=PipeInputSpec.make_from_blueprint(
                domain="test_domain", blueprint={"input_var": InputRequirementBlueprint(concept_code="test_domain.Text")}
            ),
            output_concept_code="test_domain.ProcessedText",
            parallel_sub_pipes=[SubPipe(pipe_code="test_pipe_1", output_name="result_1")],
            add_each_output=True,
            combined_output=None,
        )

        # Verify the PipeParallel was created correctly
        assert pipe_parallel.code == "test_parallel"
        assert pipe_parallel.domain == "test_domain"
        assert len(pipe_parallel.parallel_sub_pipes) == 1
        assert pipe_parallel.inputs.root["input_var"].concept_code == "test_domain.Text"
        assert pipe_parallel.output_concept_code == "test_domain.ProcessedText"
        assert pipe_parallel.add_each_output is True
        assert pipe_parallel.combined_output is None

    def test_pipe_parallel_needed_inputs_structure(self):
        """Test that PipeParallel needed_inputs method can be called and returns expected structure"""

        # Create PipeParallel with no sub-pipes to avoid dependency resolution
        pipe_parallel = PipeParallel(
            domain="test_domain",
            code="parallel_document_processor",
            inputs=PipeInputSpec.make_from_blueprint(
                domain="test_domain",
                blueprint={
                    "document": InputRequirementBlueprint(concept_code="test_domain.Document"),
                    "context": InputRequirementBlueprint(concept_code="test_domain.Context"),
                },
            ),
            output_concept_code="test_domain.ProcessedAnalysis",
            parallel_sub_pipes=[],  # No sub-pipes to avoid dependency issues
            add_each_output=True,
            combined_output=None,
        )

        # Test that needed_inputs method can be called
        needed_inputs = pipe_parallel.needed_inputs()

        # Verify it returns a PipeInputSpec object
        assert isinstance(needed_inputs, PipeInputSpec)
        assert hasattr(needed_inputs, "root")
        assert isinstance(needed_inputs.root, dict)
        # With no sub-pipes, should return empty inputs
        assert len(needed_inputs.root) == 0
