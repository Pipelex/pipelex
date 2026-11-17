from pathlib import Path

import pytest

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser
from tests.unit.pipelex.codegen.comment_injection_poc import LINE_BREAKS, NESTED_POSITIONS, poc_bundle, poc_field, poc_payload


class TestNestedTypeNameRefusedAtLoad:
    """The blueprint refuses a nested type name that is neither a field type nor the `Any` sentinel."""

    @pytest.mark.parametrize("line_break", LINE_BREAKS)
    @pytest.mark.parametrize("position", NESTED_POSITIONS)
    def test_proof_of_concept_bundle_is_refused_as_a_validation_error(self, tmp_path: Path, position: str, line_break: str):
        """The proof-of-concept bundle does not load: it is refused with the parser's ordinary validation error."""
        bundle = poc_bundle(position=position, type_name=poc_payload(line_break=line_break, marker=tmp_path / "MARKER"))

        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=bundle)

        assert f"{position} " in exc_info.value.message
        assert "is not a field type" in exc_info.value.message
        assert exc_info.value.validation_errors
        assert not (tmp_path / "MARKER").exists()

    @pytest.mark.parametrize("position", NESTED_POSITIONS)
    @pytest.mark.parametrize("type_name", ["Stop", "str", "any", "lit"])
    def test_unknown_name_is_refused_quoted_with_repr(self, position: str, type_name: str):
        """A name that is no field type, a concept code included, is refused, and the refusal quotes it with `repr`."""
        with pytest.raises(ValueError, match=f"{position} {type_name!r} is not a field type"):
            ConceptStructureBlueprint.model_validate(poc_field(position=position, type_name=type_name))

    @pytest.mark.parametrize("position", NESTED_POSITIONS)
    @pytest.mark.parametrize(
        "type_name", [*(field_type.value for field_type in ConceptStructureBlueprintFieldType if field_type != "concept"), "Any"]
    )
    def test_field_types_and_the_any_sentinel_are_admitted(self, position: str, type_name: str):
        """Every field type and the `Any` sentinel load as a nested type name."""
        blueprint = ConceptStructureBlueprint.model_validate(poc_field(position=position, type_name=type_name))

        assert getattr(blueprint, position) == type_name

    def test_list_of_concepts_is_still_admitted(self):
        """A list of concepts names `concept` as its item type, with its item concept ref."""
        blueprint = ConceptStructureBlueprint(
            description="stops", type=ConceptStructureBlueprintFieldType.LIST, item_type="concept", item_concept_ref="Stop"
        )

        assert blueprint.item_concept_ref == "Stop"
