import pytest

from pipelex.codegen.native_expansion import materialize_native_concept, reflect_native_structure
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode

STRUCTURELESS_BY_DESIGN = {NativeConceptCode.DYNAMIC, NativeConceptCode.ANYTHING, NativeConceptCode.COMPOSITE}


class TestNativeExpansion:
    """Materialization is a lookup into the pinned normative definitions; reflection is the consistency probe."""

    @pytest.mark.parametrize("native_code", list(NativeConceptCode))
    def test_pinned_blueprint_matches_runtime_content_class(self, native_code: NativeConceptCode):
        """The consistency guarantee: each runtime content class still matches its pinned blueprint.

        The pinned definitions (mthds spec `native-concepts.md`) are the authority for crate
        materialization; this probe reflects the runtime class and compares, so a runtime change
        that drifts from the standard fails loudly here.
        """
        pinned = materialize_native_concept(native_code)
        reflected = reflect_native_structure(native_code)
        if native_code in STRUCTURELESS_BY_DESIGN:
            assert pinned.structure is None
            assert reflected is None
        else:
            assert pinned.structure is not None, f"{native_code} must carry a pinned structure"
            assert reflected == pinned.structure, f"{native_code}: runtime content class drifted from its pinned blueprint"

    @pytest.mark.parametrize("native_code", list(NativeConceptCode))
    def test_pinned_description_matches_concept_factory(self, native_code: NativeConceptCode):
        """The pinned description and the runtime native concept's description are the same string (both are hashed surfaces)."""
        pinned = materialize_native_concept(native_code)
        runtime_description = ConceptFactory.make_native_concept(native_concept_code=native_code).description
        assert pinned.description == runtime_description

    def test_image_is_flat_with_paired_pixel_dimensions(self):
        """`Image` pins flat `width`/`height` integer fields — the nested size object is gone (D11 resolution)."""
        blueprint = materialize_native_concept(NativeConceptCode.IMAGE)
        assert isinstance(blueprint.structure, dict)
        assert "size" not in blueprint.structure
        assert {"url", "public_url", "mime_type", "caption", "width", "height", "filename"} <= set(blueprint.structure.keys())
        url_field = blueprint.structure["url"]
        assert isinstance(url_field, ConceptStructureBlueprint)
        assert url_field.type == ConceptStructureBlueprintFieldType.TEXT
        assert url_field.required is True
        for dimension in ("width", "height"):
            dimension_field = blueprint.structure[dimension]
            assert isinstance(dimension_field, ConceptStructureBlueprint)
            assert dimension_field.type == ConceptStructureBlueprintFieldType.INTEGER
            assert dimension_field.required is False

    def test_date_pins_real_structure_with_time_field(self):
        """`Date` is no longer structureless: `date` is a required date, `time` an optional `time` field."""
        blueprint = materialize_native_concept(NativeConceptCode.DATE)
        assert isinstance(blueprint.structure, dict)
        assert set(blueprint.structure.keys()) == {"date", "time"}
        date_field = blueprint.structure["date"]
        assert isinstance(date_field, ConceptStructureBlueprint)
        assert date_field.type == ConceptStructureBlueprintFieldType.DATE
        assert date_field.required is True
        time_field = blueprint.structure["time"]
        assert isinstance(time_field, ConceptStructureBlueprint)
        assert time_field.type == ConceptStructureBlueprintFieldType.TIME
        assert time_field.required is False

    def test_time_pins_single_required_time_field(self):
        blueprint = materialize_native_concept(NativeConceptCode.TIME)
        assert isinstance(blueprint.structure, dict)
        assert set(blueprint.structure.keys()) == {"time"}
        time_field = blueprint.structure["time"]
        assert isinstance(time_field, ConceptStructureBlueprint)
        assert time_field.type == ConceptStructureBlueprintFieldType.TIME
        assert time_field.required is True

    def test_json_dict_uses_spec_vocabulary_spellings(self):
        """The pinned JSON dict uses the spec vocabulary key type (`text`) and the reserved `Any` value marker."""
        blueprint = materialize_native_concept(NativeConceptCode.JSON)
        assert isinstance(blueprint.structure, dict)
        json_field = blueprint.structure["json_obj"]
        assert isinstance(json_field, ConceptStructureBlueprint)
        assert json_field.type == ConceptStructureBlueprintFieldType.DICT
        assert json_field.key_type == "text"
        assert json_field.value_type == "Any"
        assert json_field.required is True
