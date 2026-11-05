import re
from typing import Any, cast

import pytest
from pydantic import BaseModel

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.concepts.structure_generation.exceptions import ConceptStructureGeneratorError
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.core.stuffs.structured_content import StructuredContent
from tests.unit.pipelex.core.concepts.structure_generation.test_data import ShadowingFieldCase, ShadowingFieldNamesTestData

_DOMAIN = ShadowingFieldNamesTestData.FORWARD_REF_DOMAIN
_CLASS_NAME = f"{_DOMAIN}__Shadowing"


def _generate(structure: dict[str, ConceptStructureBlueprint]) -> tuple[str, type[BaseModel]]:
    source, generated_class = StructureGenerator(local_domain=_DOMAIN).generate_from_structure_blueprint(
        class_name=_CLASS_NAME, structure_blueprint=structure
    )
    return source, cast("type[BaseModel]", generated_class)


def _assert_holds_and_round_trips(*, generated_class: type[BaseModel], payload: dict[str, Any], expected_values: dict[str, Any]) -> None:
    instance = generated_class.model_validate(payload)
    for field_name, expected_value in expected_values.items():
        assert getattr(instance, field_name) == expected_value
    assert generated_class.model_validate(instance.model_dump(mode="json")) == instance
    assert generated_class.model_validate_json(instance.model_dump_json()) == instance


class TestStructureGeneratorShadowingFields:
    # A field named `dict` also shadows pydantic's deprecated `BaseModel.dict`, which pydantic warns about; that is not
    # the name the class body reads, which is what this test is about.
    @pytest.mark.filterwarnings('ignore:Field name "dict" in .* shadows an attribute in parent:UserWarning')
    @pytest.mark.parametrize("case", ShadowingFieldNamesTestData.READ_NAME_CASES, ids=lambda case: case.shadowed_name)
    def test_a_field_named_like_a_name_the_class_reads_gets_that_name_aliased(self, case: ShadowingFieldCase):
        """A field named like a module-level name the class body reads builds, holds its values and round-trips."""
        source, generated_class = _generate(case.structure)

        alias = f"_{case.shadowed_name}"
        assert f" import {case.shadowed_name} as {alias}\n" in source
        assert f"    {case.shadowed_name}: " in source
        # The class body reads the name through its alias only: its own spelling is the field's declaration alone.
        class_body = source.split(f"class {_CLASS_NAME}(StructuredContent):", maxsplit=1)[1]
        assert re.findall(rf"(?<![\w.]){re.escape(case.shadowed_name)}\b", class_body) == [case.shadowed_name]
        assert re.findall(rf"\b{re.escape(alias)}\b", class_body)
        assert issubclass(generated_class, StructuredContent)
        assert list(generated_class.model_fields) == list(case.structure)
        _assert_holds_and_round_trips(generated_class=generated_class, payload=case.payload, expected_values=case.expected_values)

    @pytest.mark.parametrize("case", ShadowingFieldNamesTestData.UNREAD_NAME_CASES, ids=lambda case: case.shadowed_name)
    def test_a_field_named_like_a_name_the_class_never_reads_leaves_the_source_as_it_is(self, case: ShadowingFieldCase):
        """A field named like a name the class body never reads, the base class's included, needs no alias."""
        source, generated_class = _generate(case.structure)

        assert " as _" not in source
        assert f'    {case.shadowed_name}: str = Field(..., description="A field")' in source
        assert issubclass(generated_class, StructuredContent)
        _assert_holds_and_round_trips(generated_class=generated_class, payload=case.payload, expected_values=case.expected_values)

    def test_a_temporal_default_is_rebuilt_through_the_alias_of_its_type(self):
        """A field named like its temporal type rebuilds its default through that type's alias."""
        source, generated_class = _generate(ShadowingFieldNamesTestData.TEMPORAL_DEFAULTS_STRUCTURE)

        assert 'date: _date = Field(default=_date.fromisoformat("2026-07-07"), description="A field")' in source
        assert 'datetime: _datetime = Field(default=_datetime.fromisoformat("2026-07-07T15:40:00+02:00"), description="A field")' in source
        assert 'time: _time = Field(default=_time.fromisoformat("15:40:00"), description="A field")' in source
        for field_name, expected_default in ShadowingFieldNamesTestData.TEMPORAL_DEFAULTS.items():
            assert generated_class.model_fields[field_name].default == expected_default
        instance = generated_class.model_validate({})
        assert instance.model_dump() == ShadowingFieldNamesTestData.TEMPORAL_DEFAULTS
        assert generated_class.model_validate_json(instance.model_dump_json()) == instance

    def test_the_source_is_a_module_that_builds_the_class_on_its_own(self):
        """The emitted module imports every name its class body reads, aliases included, with nothing provided to it."""
        case = ShadowingFieldNamesTestData.READ_NAME_CASES[0]
        source, _ = _generate(case.structure)

        namespace: dict[str, Any] = {}
        exec(compile(source, "<shadowing>", "exec"), namespace)
        rebuilt_class = cast("type[BaseModel]", namespace[_CLASS_NAME])
        _assert_holds_and_round_trips(generated_class=rebuilt_class, payload=case.payload, expected_values=case.expected_values)

    @pytest.mark.parametrize(("topic", "structure"), ShadowingFieldNamesTestData.FORWARD_REF_STRUCTURES)
    def test_a_field_named_like_a_class_the_structure_refers_to_is_refused(self, topic: str, structure: dict[str, ConceptStructureBlueprint]):
        """No alias can stand for a forward reference, so the field is refused with a finding naming it and the concept."""
        with pytest.raises(ConceptStructureGeneratorError) as exc_info:
            _generate(structure)

        assert exc_info.value.given_params == {"finding": ShadowingFieldNamesTestData.FORWARD_REF_FINDING}, topic
        assert exc_info.value.message == f"Cannot generate the structure class '{_CLASS_NAME}': {ShadowingFieldNamesTestData.FORWARD_REF_FINDING}."
