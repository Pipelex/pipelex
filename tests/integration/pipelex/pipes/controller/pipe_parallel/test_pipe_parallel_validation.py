from typing import Callable

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.method_hub import get_concept_library, get_pipe_library
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class TestPipeParallelValidation:
    """Tests for PipeParallel creation and basic structure"""

    def test_pipe_parallel_with_real_pipe_structure(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        # Create a real PipeLLM that will infer inputs from the prompt template
        domain_code = "test_domain"
        concept_library = get_concept_library()
        concept_blueprint = ConceptBlueprint(description="A test document")
        concept_1 = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="TestDocument",
            blueprint_or_string_description=concept_blueprint,
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Context",
            blueprint_or_string_description=concept_blueprint,
        )
        concept_3 = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Analysis",
            blueprint_or_string_description=concept_blueprint,
        )
        concept_library.add_concepts(concepts=[concept_1, concept_2, concept_3])

        pipe_llm_blueprint = PipeLLMBlueprint(
            inputs={
                "document": concept_1.concept_ref,
                "context": concept_2.concept_ref,
            },
            description="Analysis pipe for document processing",
            output=ConceptFactory.make_concept_ref_with_domain(domain_code=domain_code, concept_code=concept_3.code),
            prompt="Analyze this document:  \n@context\n@document",
        )

        real_pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="analyze_document",
            blueprint=pipe_llm_blueprint,
            concept_codes_from_the_same_domain=[concept_1.code, concept_2.code, concept_3.code],
        )

        pipe_library = get_pipe_library()
        pipe_library.add_new_pipe(pipe=real_pipe)

        # Verify the real pipe was created successfully
        assert real_pipe.domain_code == domain_code
        assert real_pipe.output.concept.code == concept_3.code
        assert real_pipe.output.concept.domain_code == domain_code

        # Create PipeParallel that would reference this pipe
        pipe_parallel_blueprint = PipeParallelBlueprint(
            description="Parallel document processor for testing",
            inputs={
                "document": concept_1.code,
                "context": concept_2.code,
            },
            output=ConceptFactory.make_concept_ref_with_domain(domain_code=domain_code, concept_code=concept_3.code),
            branches=[SubPipeBlueprint(pipe=real_pipe.code, result="analysis_result")],
            add_each_output=True,
        )

        pipe_parallel = PipeFactory[PipeParallel].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="parallel_document_processor",
            blueprint=pipe_parallel_blueprint,
            concept_codes_from_the_same_domain=[concept_1.code, concept_2.code, concept_3.code],
        )

        # Verify the PipeParallel structure is correct
        assert len(pipe_parallel.parallel_sub_pipes) == 1
        assert pipe_parallel.parallel_sub_pipes[0].pipe_code == "analyze_document"
        assert pipe_parallel.parallel_sub_pipes[0].output_name == "analysis_result"

        # Verify PipeParallel has the expected structure
        assert pipe_parallel.domain_code == domain_code
        assert pipe_parallel.code == "parallel_document_processor"
        assert pipe_parallel.add_each_output is True

        concept_library.teardown()

    def test_pipe_parallel_creation(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test basic PipeParallel creation and structure"""
        # Create a simple PipeParallel with proper inputs
        domain_code = "test_domain"
        concept_library = get_concept_library()
        concept_blueprint = ConceptBlueprint(description="Lorem Ipsum")
        concept_1 = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="TestDocument",
            blueprint_or_string_description=concept_blueprint,
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Context",
            blueprint_or_string_description=concept_blueprint,
        )
        concept_3 = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="ProcessedAnalysis",
            blueprint_or_string_description=concept_blueprint,
        )
        concept_library.add_concepts(concepts=[concept_1, concept_2, concept_3])

        pipe_parallel_blueprint = PipeParallelBlueprint(
            description="Basic parallel pipe for testing",
            inputs={"input_var": concept_1.concept_ref},
            output=ConceptFactory.make_concept_ref_with_domain(domain_code=domain_code, concept_code=concept_3.code),
            branches=[SubPipeBlueprint(pipe="test_pipe_1", result="result_1")],
            add_each_output=True,
        )

        pipe_parallel = PipeFactory[PipeParallel].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_parallel",
            blueprint=pipe_parallel_blueprint,
            concept_codes_from_the_same_domain=[concept_1.code, concept_2.code, concept_3.code],
        )

        # Verify the PipeParallel was created correctly
        assert pipe_parallel.code == "test_parallel"
        assert pipe_parallel.domain_code == domain_code
        assert len(pipe_parallel.parallel_sub_pipes) == 1
        assert pipe_parallel.inputs.root["input_var"].concept.code == concept_1.code
        assert pipe_parallel.output.concept.code == concept_3.code
        assert pipe_parallel.output.concept.domain_code == domain_code
        assert pipe_parallel.add_each_output is True

        concept_library.teardown()

    def test_pipe_parallel_needed_inputs_structure(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test that PipeParallel needed_inputs method can be called and returns expected structure"""
        domain_code = "test_domain"
        concept_library = get_concept_library()
        concept_blueprint = ConceptBlueprint(description="A test document")
        concept_1 = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="TestDocument",
            blueprint_or_string_description=concept_blueprint,
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="Context",
            blueprint_or_string_description=concept_blueprint,
        )
        concept_3 = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="ProcessedAnalysis",
            blueprint_or_string_description=concept_blueprint,
        )
        concept_library.add_concepts(concepts=[concept_1, concept_2, concept_3])

        # Create PipeParallel with no sub-pipes to avoid dependency resolution
        pipe_parallel_blueprint = PipeParallelBlueprint(
            description="Parallel processor for testing inputs structure",
            inputs={
                "document": concept_1.concept_ref,
                "context": concept_2.concept_ref,
            },
            output=ConceptFactory.make_concept_ref_with_domain(domain_code=domain_code, concept_code=concept_3.code),
            branches=[],  # No sub-pipes to avoid dependency issues
            add_each_output=True,
        )

        pipe_parallel = PipeFactory[PipeParallel].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="parallel_document_processor",
            blueprint=pipe_parallel_blueprint,
            concept_codes_from_the_same_domain=[concept_1.code, concept_2.code, concept_3.code],
        )

        # Test that needed_inputs method can be called
        needed_inputs = pipe_parallel.needed_inputs()

        # Verify it returns a InputStuffSpecs object
        assert isinstance(needed_inputs, InputStuffSpecs)
        assert hasattr(needed_inputs, "root")
        assert isinstance(needed_inputs.root, dict)
        # With no sub-pipes, should return empty inputs
        assert len(needed_inputs.root) == 0

        concept_library.teardown()
