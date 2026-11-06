import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.exceptions import ConceptFactoryError
from pipelex.core.concepts.structure_generation.exceptions import ConceptStructureGeneratorError
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.errors.problem import ProblemView

_DOMAIN = "shadow_refusal"
_FORWARD_REF_FINDING = (
    "its field 'shadow_refusal__Person' has the name of the Python class of the concept 'shadow_refusal.Person', which the structure refers to"
)


class TestStructureGenerationRefusal:
    def test_a_structure_the_generator_refuses_names_the_concept_and_the_field(self):
        """The generator's own finding reaches the caller's sentence beside the concept it refuses."""
        blueprint = ConceptBlueprint(
            description="A day",
            structure={
                "shadow_refusal__Person": ConceptStructureBlueprint(
                    description="Who", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="Person", required=True
                ),
            },
        )

        with pytest.raises(ConceptFactoryError) as exc_info:
            ConceptFactory.make_from_blueprint(domain_code=_DOMAIN, concept_code="Day", blueprint_or_string_description=blueprint)

        refusal = exc_info.value
        assert isinstance(refusal.__cause__, ConceptStructureGeneratorError)
        assert refusal.given_params == {"concept": f"{_DOMAIN}.Day", "finding": _FORWARD_REF_FINDING}
        assert refusal.resolve_error_code() == CoreCode.METHOD_CONCEPT_INVALID
        problem = refusal.to_problem(view=ProblemView.CALLER)
        assert problem.detail == f"The structure of the concept '{_DOMAIN}.Day' cannot be built ({_FORWARD_REF_FINDING})."

    def test_an_unexpected_failure_of_the_generated_class_names_the_concept_and_what_it_raised(self, mocker: MockerFixture):
        """A generated class that fails to build for any other reason names the concept and the class of what it raised."""
        mocker.patch.object(StructureGenerator, "validate_generated_code", side_effect=TypeError("an unexpected failure"))
        blueprint = ConceptBlueprint(
            description="A day",
            structure={"day": ConceptStructureBlueprint(description="The day", type=ConceptStructureBlueprintFieldType.DATE, required=True)},
        )

        with pytest.raises(ConceptFactoryError) as exc_info:
            ConceptFactory.make_from_blueprint(domain_code=_DOMAIN, concept_code="Day", blueprint_or_string_description=blueprint)

        refusal = exc_info.value
        finding = "generating its Python class raised TypeError"
        assert refusal.given_params == {"concept": f"{_DOMAIN}.Day", "finding": finding}
        assert refusal.resolve_error_code() == CoreCode.METHOD_CONCEPT_INVALID
        problem = refusal.to_problem(view=ProblemView.CALLER)
        assert problem.detail == f"The structure of the concept '{_DOMAIN}.Day' cannot be built ({finding})."
        assert "an unexpected failure" not in problem.model_dump_json()
