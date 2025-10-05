from pipelex.core.concepts.concept_factory import ConceptBlueprint, ConceptFactory
from pipelex.core.pipes.input_requirement_blueprint import InputRequirementBlueprint
from pipelex.hub import get_concept_library
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_factory import PipeSequenceFactory
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint


class TestPipeSequenceValidation:
    """Tests for PipeSequence validate_inputs method"""

    def test_pipe_sequence_creation(self):
        """Test basic PipeSequence creation"""
        domain = "test_domain"
        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="TestConcept",
            domain=domain,
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
            concept_codes_from_the_same_domain=["TestConcept"],
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            concept_code="ProcessedText",
            domain=domain,
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
            concept_codes_from_the_same_domain=["ProcessedText"],
        )
        concept_library = get_concept_library()
        concept_library.add_concepts([concept_1, concept_2])

        pipe_sequence_blueprint = PipeSequenceBlueprint(
            description="Test sequence for validation",
            inputs={"text": InputRequirementBlueprint(concept=concept_1.concept_string)},
            output=concept_2.concept_string,
            steps=[SubPipeBlueprint(pipe="test_pipe_1", result="intermediate_result")],
        )

        pipe_sequence = PipeSequenceFactory.make_from_blueprint(
            domain=domain,
            pipe_code="test_sequence",
            blueprint=pipe_sequence_blueprint,
        )

        assert pipe_sequence.code == "test_sequence"
        assert pipe_sequence.domain == domain
        assert len(pipe_sequence.sequential_sub_pipes) == 1
        assert pipe_sequence.sequential_sub_pipes[0].pipe_code == "test_pipe_1"
        assert pipe_sequence.sequential_sub_pipes[0].output_name == "intermediate_result"

        concept_library.teardown()

    def test_pipe_sequence_multiple_sub_pipes(self):
        """Test PipeSequence with multiple sequential sub-pipes"""
        domain = "test_domain"
        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="TestConcept",
            domain=domain,
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
            concept_codes_from_the_same_domain=["TestConcept"],
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            concept_code="ProcessedText",
            domain=domain,
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
            concept_codes_from_the_same_domain=["ProcessedText"],
        )
        concept_library = get_concept_library()
        concept_library.add_concepts([concept_1, concept_2])

        pipe_sequence_blueprint = PipeSequenceBlueprint(
            description="Test sequence with multiple steps",
            inputs={"initial_input": InputRequirementBlueprint(concept=concept_1.concept_string)},
            output=concept_2.concept_string,
            steps=[SubPipeBlueprint(pipe="step_1", result="intermediate"), SubPipeBlueprint(pipe="step_2", result="final_output")],
        )

        pipe_sequence = PipeSequenceFactory.make_from_blueprint(
            domain=domain,
            pipe_code="test_sequence",
            blueprint=pipe_sequence_blueprint,
        )

        assert pipe_sequence.code == "test_sequence"
        assert len(pipe_sequence.sequential_sub_pipes) == 2
        assert pipe_sequence.inputs.root["initial_input"].concept.code == concept_1.code

        concept_library.teardown()
