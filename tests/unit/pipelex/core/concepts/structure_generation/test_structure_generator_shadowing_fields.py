from typing import Any, cast

import pytest
from pydantic import BaseModel

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.concepts.structure_generation.exceptions import ConceptStructureGeneratorError
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.core.stuffs.structured_content import StructuredContent
from tests.unit.pipelex.core.concepts.structure_generation.cases import ShadowingFieldCase, ShadowingFieldNamesCases

_DOMAIN = ShadowingFieldNamesCases.FORWARD_REF_DOMAIN
_CLASS_NAME = f"{_DOMAIN}__Shadowing"


def _generate(structure: dict[str, ConceptStructureBlueprint]) -> type[BaseModel]:
    generated_class = StructureGenerator(local_domain=_DOMAIN).generate_from_structure_blueprint(
        class_name=_CLASS_NAME, structure_blueprint=structure
    )
    return cast("type[BaseModel]", generated_class)


def _assert_holds_and_round_trips(*, generated_class: type[BaseModel], payload: dict[str, Any], expected_values: dict[str, Any]) -> None:
    instance = generated_class.model_validate(payload)
    for field_name, expected_value in expected_values.items():
        assert getattr(instance, field_name) == expected_value
    assert generated_class.model_validate(instance.model_dump(mode="json")) == instance
    assert generated_class.model_validate_json(instance.model_dump_json()) == instance


class TestStructureGeneratorShadowingFields:
    """A class built from data reads no name, so a field named like a type, a class or a helper shadows nothing."""

    # A field named `dict` also shadows pydantic's deprecated `BaseModel.dict`, which pydantic warns about; that is not
    # what this test is about.
    @pytest.mark.filterwarnings('ignore:Field name "dict" in .* shadows an attribute in parent:UserWarning')
    @pytest.mark.parametrize(
        "case",
        [*ShadowingFieldNamesCases.READ_NAME_CASES, *ShadowingFieldNamesCases.UNREAD_NAME_CASES],
        ids=lambda case: case.shadowed_name,
    )
    def test_a_field_named_like_a_module_level_name_builds_holds_and_round_trips(self, case: ShadowingFieldCase):
        """A field named like a type or a class the annotations use builds, holds its values and round-trips."""
        generated_class = _generate(case.structure)

        assert issubclass(generated_class, StructuredContent)
        assert list(generated_class.model_fields) == list(case.structure)
        _assert_holds_and_round_trips(generated_class=generated_class, payload=case.payload, expected_values=case.expected_values)

    def test_a_field_named_like_its_temporal_type_keeps_its_default(self):
        """A field named like its temporal type holds its default as a value of that type."""
        generated_class = _generate(ShadowingFieldNamesCases.TEMPORAL_DEFAULTS_STRUCTURE)

        for field_name, expected_default in ShadowingFieldNamesCases.TEMPORAL_DEFAULTS.items():
            assert generated_class.model_fields[field_name].default == expected_default
        instance = generated_class.model_validate({})
        assert instance.model_dump() == ShadowingFieldNamesCases.TEMPORAL_DEFAULTS
        assert generated_class.model_validate_json(instance.model_dump_json()) == instance

    @pytest.mark.parametrize(("topic", "structure"), ShadowingFieldNamesCases.FORWARD_REF_STRUCTURES)
    def test_a_field_named_like_a_class_the_structure_refers_to_is_refused(self, topic: str, structure: dict[str, ConceptStructureBlueprint]):
        """A forward reference is resolved by its name, which the field would shadow: the field is refused, naming it and the concept."""
        with pytest.raises(ConceptStructureGeneratorError) as exc_info:
            _generate(structure)

        assert exc_info.value.given_params == {"finding": ShadowingFieldNamesCases.FORWARD_REF_FINDING}, topic
        assert exc_info.value.message == f"Cannot generate the structure class '{_CLASS_NAME}': {ShadowingFieldNamesCases.FORWARD_REF_FINDING}."
