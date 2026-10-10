"""A generated field admits `None` only when it may hold nothing: when it is neither `required` nor defaulted.

That is the standard's rule, and a binding step derives a read's presence from it alone, so a generated class
that admitted `None` anywhere else would hold an absence its readers ruled out.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.resolved_fields import resolve_field
from pipelex.core.concepts.structure_generation.generator import StructureGenerator


def _generate(structure_blueprint: dict[str, ConceptStructureBlueprint]) -> tuple[str, Any]:
    return StructureGenerator(local_domain="presence").generate_from_structure_blueprint(
        class_name="PresenceModel", structure_blueprint=structure_blueprint
    )


class TestStructureGeneratorPresence:
    @pytest.mark.parametrize(
        ("field_blueprint", "may_hold_nothing"),
        [
            (ConceptStructureBlueprint(description="optional", type=ConceptStructureBlueprintFieldType.TEXT), True),
            (ConceptStructureBlueprint(description="required", type=ConceptStructureBlueprintFieldType.TEXT, required=True), False),
            (ConceptStructureBlueprint(description="defaulted", type=ConceptStructureBlueprintFieldType.TEXT, default_value="x"), False),
            (ConceptStructureBlueprint(description="defaulted false", type=ConceptStructureBlueprintFieldType.BOOLEAN, default_value=False), False),
            (ConceptStructureBlueprint(description="defaulted choice", choices=["a", "b"], default_value="a"), False),
        ],
    )
    def test_the_blueprint_and_the_resolved_field_state_the_same_rule(self, field_blueprint: ConceptStructureBlueprint, may_hold_nothing: bool):
        assert field_blueprint.may_hold_nothing is may_hold_nothing
        assert resolve_field(field_name="field", blueprint=field_blueprint).may_hold_nothing is may_hold_nothing

    def test_a_defaulted_field_takes_its_default_and_refuses_null(self):
        source, generated_class = _generate(
            {"note": ConceptStructureBlueprint(description="a note", type=ConceptStructureBlueprintFieldType.TEXT, default_value="fallback")}
        )

        assert '    note: str = Field(default="fallback", description="a note")' in source
        assert generated_class.model_validate({}).note == "fallback"
        assert generated_class.model_validate({"note": "written"}).note == "written"
        with pytest.raises(ValidationError) as exc_info:
            generated_class.model_validate({"note": None})
        assert [error["loc"] for error in exc_info.value.errors()] == [("note",)]

    def test_a_defaulted_falsy_value_is_still_a_default(self):
        """`default_value = false` is a default like any other, so the field is not nullable either."""
        source, generated_class = _generate(
            {"enabled": ConceptStructureBlueprint(description="on", type=ConceptStructureBlueprintFieldType.BOOLEAN, default_value=False)}
        )

        assert "    enabled: bool = Field(default=False" in source
        with pytest.raises(ValidationError):
            generated_class.model_validate({"enabled": None})

    def test_a_field_that_may_hold_nothing_keeps_an_explicit_null(self):
        source, generated_class = _generate({"note": ConceptStructureBlueprint(description="a note", type=ConceptStructureBlueprintFieldType.TEXT)})

        assert "    note: str | None = Field(default=None" in source
        assert generated_class.model_validate({"note": None}).note is None
        assert generated_class.model_validate({}).note is None

    @pytest.mark.parametrize("value", ["text", 0, False, [1, "two"], {"key": "value"}, {}])
    def test_a_required_anything_field_holds_any_value_but_null(self, value: Any):
        source, generated_class = _generate(
            {
                "payload": ConceptStructureBlueprint(
                    description="any value", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="native.Anything", required=True
                )
            }
        )

        assert "from pipelex.core.stuffs.non_null_any import NonNullAny" in source
        assert "    payload: NonNullAny = Field(..., description=" in source
        assert generated_class.model_validate({"payload": value}).payload == value
        with pytest.raises(ValidationError) as exc_info:
            generated_class.model_validate({"payload": None})
        assert [(error["loc"], error["type"]) for error in exc_info.value.errors()] == [(("payload",), "null_value")]

    def test_a_required_anything_field_keeps_an_open_schema(self):
        """The schema is what a model is asked for, and the strict modes that would read `not` refuse it."""
        _, generated_class = _generate(
            {
                "payload": ConceptStructureBlueprint(
                    description="any value", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="native.Anything", required=True
                )
            }
        )

        schema = generated_class.model_json_schema()
        assert schema["properties"]["payload"] == {"description": "any value", "title": "Payload"}
        assert schema["required"] == ["payload"]

    def test_an_optional_anything_field_may_hold_nothing(self):
        source, generated_class = _generate(
            {
                "payload": ConceptStructureBlueprint(
                    description="any value", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="native.Anything"
                )
            }
        )

        assert "    payload: Any | None = Field(default=None" in source
        assert "NonNullAny" not in source
        assert generated_class.model_validate({"payload": None}).payload is None
