from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.input_requirement_blueprint import InputRequirementBlueprint
from pipelex.core.pipes.input_requirements import InputRequirements
from pipelex.hub import get_concept_library, get_pipe_library
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_factory import PipeParallelFactory
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.llm.pipe_llm_factory import PipeLLMFactory


class TestPipeParallelValidation:
    """Tests for PipeParallel creation and basic structure"""

    def test_pipe_parallel_with_real_pipe_structure(self):
        """Test PipeParallel structure with a real pipe"""
        # Create a real PipeLLM that will infer inputs from the prompt template
        domain = "test_domain"
        concept_library = get_concept_library()
        concept_blueprint = ConceptBlueprint(description="A test document")
        concept_1 = ConceptFactory.make_from_blueprint(
            domain=domain,
            concept_code="Document",
            blueprint=concept_blueprint,
            concept_codes_from_the_same_domain=["Document"],
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            domain=domain,
            concept_code="Context",
            blueprint=concept_blueprint,
            concept_codes_from_the_same_domain=["Context"],
        )
        concept_3 = ConceptFactory.make_from_blueprint(
            domain=domain,
            concept_code="Analysis",
            blueprint=concept_blueprint,
            concept_codes_from_the_same_domain=["Analysis"],
        )
        concept_library.add_concepts(concepts=[concept_1, concept_2, concept_3])

        pipe_llm_blueprint = PipeLLMBlueprint(
            inputs={
                "document": InputRequirementBlueprint(concept=concept_1.concept_string),
                "context": InputRequirementBlueprint(concept=concept_2.concept_string),
            },
            description="Analysis pipe for document processing",
            output=ConceptFactory.make_concept_string_with_domain(domain=domain, concept_code=concept_3.code),
            prompt="Analyze this document:  \n@context\n@document",
        )

        real_pipe = PipeLLMFactory.make_from_blueprint(
            domain=domain,
            pipe_code="analyze_document",
            blueprint=pipe_llm_blueprint,
        )

        pipe_library = get_pipe_library()
        pipe_library.add_new_pipe(pipe=real_pipe)

        # Verify the real pipe was created successfully
        assert real_pipe.domain == domain
        assert real_pipe.output.code == concept_3.code
        assert real_pipe.output.domain == domain

        # Create PipeParallel that would reference this pipe
        pipe_parallel_blueprint = PipeParallelBlueprint(
            description="Parallel document processor for testing",
            inputs={
                "document": InputRequirementBlueprint(concept=concept_1.code),
                "context": InputRequirementBlueprint(concept=concept_2.code),
            },
            output=ConceptFactory.make_concept_string_with_domain(domain=domain, concept_code=concept_3.code),
            parallels=[SubPipeBlueprint(pipe=real_pipe.code, result="analysis_result")],
            add_each_output=True,
            combined_output=None,
        )

        pipe_parallel = PipeParallelFactory.make_from_blueprint(
            domain=domain,
            pipe_code="parallel_document_processor",
            blueprint=pipe_parallel_blueprint,
        )

        # Verify the PipeParallel structure is correct
        assert len(pipe_parallel.parallel_sub_pipes) == 1
        assert pipe_parallel.parallel_sub_pipes[0].pipe_code == "analyze_document"
        assert pipe_parallel.parallel_sub_pipes[0].output_name == "analysis_result"

        # Verify PipeParallel has the expected structure
        assert pipe_parallel.domain == domain
        assert pipe_parallel.code == "parallel_document_processor"
        assert pipe_parallel.add_each_output is True

        concept_library.teardown()

    def test_pipe_parallel_creation(self):
        """Test basic PipeParallel creation and structure"""
        # Create a simple PipeParallel with proper inputs
        domain = "test_domain"
        concept_library = get_concept_library()
        concept_blueprint = ConceptBlueprint(description="Lorem Ipsum")
        concept_1 = ConceptFactory.make_from_blueprint(
            domain=domain,
            concept_code="Document",
            blueprint=concept_blueprint,
            concept_codes_from_the_same_domain=["Document"],
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            domain=domain,
            concept_code="Context",
            blueprint=concept_blueprint,
            concept_codes_from_the_same_domain=["Context"],
        )
        concept_3 = ConceptFactory.make_from_blueprint(
            domain=domain,
            concept_code="ProcessedAnalysis",
            blueprint=concept_blueprint,
            concept_codes_from_the_same_domain=["ProcessedAnalysis"],
        )
        concept_library.add_concepts(concepts=[concept_1, concept_2, concept_3])

        pipe_parallel_blueprint = PipeParallelBlueprint(
            description="Basic parallel pipe for testing",
            inputs={"input_var": InputRequirementBlueprint(concept=concept_1.concept_string)},
            output=ConceptFactory.make_concept_string_with_domain(domain=domain, concept_code=concept_3.code),
            parallels=[SubPipeBlueprint(pipe="test_pipe_1", result="result_1")],
            add_each_output=True,
            combined_output=None,
        )

        pipe_parallel = PipeParallelFactory.make_from_blueprint(
            domain=domain,
            pipe_code="test_parallel",
            blueprint=pipe_parallel_blueprint,
        )

        # Verify the PipeParallel was created correctly
        assert pipe_parallel.code == "test_parallel"
        assert pipe_parallel.domain == domain
        assert len(pipe_parallel.parallel_sub_pipes) == 1
        assert pipe_parallel.inputs.root["input_var"].concept.code == concept_1.code
        assert pipe_parallel.output.code == concept_3.code
        assert pipe_parallel.output.domain == domain
        assert pipe_parallel.add_each_output is True
        assert pipe_parallel.combined_output is None

        concept_library.teardown()

    def test_pipe_parallel_needed_inputs_structure(self):
        """Test that PipeParallel needed_inputs method can be called and returns expected structure"""
        domain = "test_domain"
        concept_library = get_concept_library()
        concept_blueprint = ConceptBlueprint(description="A test document")
        concept_1 = ConceptFactory.make_from_blueprint(
            domain=domain,
            concept_code="Document",
            blueprint=concept_blueprint,
            concept_codes_from_the_same_domain=["Document"],
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            domain=domain,
            concept_code="Context",
            blueprint=concept_blueprint,
            concept_codes_from_the_same_domain=["Context"],
        )
        concept_3 = ConceptFactory.make_from_blueprint(
            domain=domain,
            concept_code="ProcessedAnalysis",
            blueprint=concept_blueprint,
            concept_codes_from_the_same_domain=["ProcessedAnalysis"],
        )
        concept_library.add_concepts(concepts=[concept_1, concept_2, concept_3])

        # Create PipeParallel with no sub-pipes to avoid dependency resolution
        pipe_parallel_blueprint = PipeParallelBlueprint(
            description="Parallel processor for testing inputs structure",
            inputs={
                "document": InputRequirementBlueprint(concept=concept_1.concept_string),
                "context": InputRequirementBlueprint(concept=concept_2.concept_string),
            },
            output=ConceptFactory.make_concept_string_with_domain(domain=domain, concept_code=concept_3.code),
            parallels=[],  # No sub-pipes to avoid dependency issues
            add_each_output=True,
            combined_output=None,
        )

        pipe_parallel = PipeParallelFactory.make_from_blueprint(
            domain=domain,
            pipe_code="parallel_document_processor",
            blueprint=pipe_parallel_blueprint,
        )

        # Test that needed_inputs method can be called
        needed_inputs = pipe_parallel.needed_inputs()

        # Verify it returns a PipeInput object
        assert isinstance(needed_inputs, InputRequirements)
        assert hasattr(needed_inputs, "root")
        assert isinstance(needed_inputs.root, dict)
        # With no sub-pipes, should return empty inputs
        assert len(needed_inputs.root) == 0

        concept_library.teardown()
