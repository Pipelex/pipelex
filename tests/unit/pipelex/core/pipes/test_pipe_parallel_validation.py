from pipelex.core.pipes.pipe_input_spec import InputRequirementBlueprint, PipeInputSpec
from pipelex.pipe_controllers.pipe_parallel_factory import PipeParallelBlueprint, PipeParallelFactory
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint
from pipelex.pipe_operators.pipe_llm_factory import PipeLLMBlueprint, PipeLLMFactory


class TestPipeParallelValidation:
    """Tests for PipeParallel creation and basic structure"""

    def test_pipe_parallel_with_real_pipe_structure(self):
        """Test PipeParallel structure with a real pipe"""
        # Create a real PipeLLM that will infer inputs from the prompt template
        pipe_llm_blueprint = PipeLLMBlueprint(
            definition="Analysis pipe for document processing",
            output="test_domain.Analysis",
            prompt_template="Analyze this document:  \n@context\n@document",
        )

        real_pipe = PipeLLMFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code="analyze_document",
            pipe_blueprint=pipe_llm_blueprint,
        )

        # Verify the real pipe was created successfully
        assert real_pipe.code == "analyze_document"
        assert real_pipe.domain == "test_domain"
        assert real_pipe.output.code == "test_domain.Analysis"

        # Create PipeParallel that would reference this pipe
        pipe_parallel_blueprint = PipeParallelBlueprint(
            definition="Parallel document processor for testing",
            inputs={
                "document": InputRequirementBlueprint(concept_code="test_domain.document"),
                "context": InputRequirementBlueprint(concept_code="test_domain.context"),
            },
            output="test_domain.ProcessedAnalysis",
            parallels=[SubPipeBlueprint(pipe="analyze_document", result="analysis_result")],
            add_each_output=True,
            combined_output=None,
        )

        pipe_parallel = PipeParallelFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code="parallel_document_processor",
            pipe_blueprint=pipe_parallel_blueprint,
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
        pipe_parallel_blueprint = PipeParallelBlueprint(
            definition="Basic parallel pipe for testing",
            inputs={"input_var": InputRequirementBlueprint(concept_code="test_domain.Text")},
            output="test_domain.ProcessedText",
            parallels=[SubPipeBlueprint(pipe="test_pipe_1", result="result_1")],
            add_each_output=True,
            combined_output=None,
        )

        pipe_parallel = PipeParallelFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code="test_parallel",
            pipe_blueprint=pipe_parallel_blueprint,
        )

        # Verify the PipeParallel was created correctly
        assert pipe_parallel.code == "test_parallel"
        assert pipe_parallel.domain == "test_domain"
        assert len(pipe_parallel.parallel_sub_pipes) == 1
        assert pipe_parallel.inputs.root["input_var"].concept.code == "test_domain.Text"
        assert pipe_parallel.output.code == "test_domain.ProcessedText"
        assert pipe_parallel.add_each_output is True
        assert pipe_parallel.combined_output is None

    def test_pipe_parallel_needed_inputs_structure(self):
        """Test that PipeParallel needed_inputs method can be called and returns expected structure"""

        # Create PipeParallel with no sub-pipes to avoid dependency resolution
        pipe_parallel_blueprint = PipeParallelBlueprint(
            definition="Parallel processor for testing inputs structure",
            inputs={
                "document": InputRequirementBlueprint(concept_code="test_domain.Document"),
                "context": InputRequirementBlueprint(concept_code="test_domain.Context"),
            },
            output="test_domain.ProcessedAnalysis",
            parallels=[],  # No sub-pipes to avoid dependency issues
            add_each_output=True,
            combined_output=None,
        )

        pipe_parallel = PipeParallelFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code="parallel_document_processor",
            pipe_blueprint=pipe_parallel_blueprint,
        )

        # Test that needed_inputs method can be called
        needed_inputs = pipe_parallel.needed_inputs()

        # Verify it returns a PipeInputSpec object
        assert isinstance(needed_inputs, PipeInputSpec)
        assert hasattr(needed_inputs, "root")
        assert isinstance(needed_inputs.root, dict)
        # With no sub-pipes, should return empty inputs
        assert len(needed_inputs.root) == 0
