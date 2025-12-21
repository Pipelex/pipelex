from pathlib import Path
from typing import Callable

from pipelex.core.concepts.concept_factory import ConceptBlueprint, ConceptFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.hub import get_concept_library
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint


class TestPipeSequenceCreation:
    """Tests for basic PipeSequence creation"""

    def test_pipe_sequence_creation(self, load_test_library: Callable[[list[Path]], None]):
        """Test basic PipeSequence creation"""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_sequence")])
        domain_code = "test_domain"
        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="TestConcept",
            domain_code=domain_code,
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum"),
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            concept_code="ProcessedText",
            domain_code=domain_code,
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum"),
        )
        concept_library = get_concept_library()
        concept_library.add_concepts([concept_1, concept_2])

        pipe_sequence_blueprint = PipeSequenceBlueprint(
            description="Test sequence for validation",
            inputs={"text": concept_1.concept_ref},
            output=concept_2.concept_ref,
            steps=[SubPipeBlueprint(pipe="test_pipe_1", result="intermediate_result")],
        )

        pipe_sequence = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_sequence",
            blueprint=pipe_sequence_blueprint,
        )

        assert pipe_sequence.code == "test_sequence"
        assert pipe_sequence.domain_code == domain_code
        assert len(pipe_sequence.sequential_sub_pipes) == 1
        assert pipe_sequence.sequential_sub_pipes[0].pipe_code == "test_pipe_1"
        assert pipe_sequence.sequential_sub_pipes[0].output_name == "intermediate_result"
        concept_library.teardown()
