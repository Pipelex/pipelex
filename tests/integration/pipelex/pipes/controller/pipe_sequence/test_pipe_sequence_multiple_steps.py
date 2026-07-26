from pathlib import Path
from typing import Callable

from pipelex.core.concepts.concept_factory import ConceptBlueprint, ConceptFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.method_hub import get_concept_library
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint


class TestPipeSequenceMultipleSteps:
    """Tests for PipeSequence with multiple steps"""

    def test_pipe_sequence_multiple_sub_pipes(self, load_test_library: Callable[[list[Path]], None]):
        """Test PipeSequence with multiple sequential sub-pipes"""
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
            description="Test sequence with multiple steps",
            inputs={"initial_input": concept_1.concept_ref},
            output=concept_2.concept_ref,
            steps=[SubPipeBlueprint(pipe="step_1", result="intermediate"), SubPipeBlueprint(pipe="step_2", result="final_output")],
        )

        pipe_sequence = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_sequence",
            blueprint=pipe_sequence_blueprint,
        )

        assert pipe_sequence.code == "test_sequence"
        assert len(pipe_sequence.sequential_sub_pipes) == 2
        assert pipe_sequence.inputs.root["initial_input"].concept.code == concept_1.code

        concept_library.teardown()
