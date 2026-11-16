import pytest

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.native.pinned_blueprints import make_pinned_native_blueprint, make_pinned_native_value_blueprint
from pipelex.core.stuffs.stored_value_content import STORED_VALUE_REFERENCE_FIELDS, StoredValueContent


class TestPinnedNativeValueBlueprint:
    @pytest.mark.parametrize(
        ("native_code", "expected_fields", "value_field_name"),
        [
            (NativeConceptCode.TEXT, ["text"], "text"),
            (NativeConceptCode.MARKDOWN, ["text"], "text"),
            (NativeConceptCode.HTML, ["inner_html", "css_class"], "inner_html"),
            (NativeConceptCode.JSON, ["json_obj"], "json_obj"),
        ],
    )
    def test_a_stored_value_native_keeps_its_value_fields_with_the_value_required(
        self, native_code: NativeConceptCode, expected_fields: list[str], value_field_name: str
    ):
        structure = make_pinned_native_value_blueprint(native_code).structure

        assert isinstance(structure, dict)
        assert list(structure) == expected_fields
        value_field = structure[value_field_name]
        assert isinstance(value_field, ConceptStructureBlueprint)
        assert value_field.required is True

    def test_every_other_native_is_its_pinned_blueprint(self):
        for native_code in NativeConceptCode:
            structure_class = native_code.structure_class
            if structure_class is not None and issubclass(structure_class, StoredValueContent):
                continue
            assert make_pinned_native_value_blueprint(native_code) == make_pinned_native_blueprint(native_code), native_code

    def test_the_stored_value_natives_are_the_ones_whose_pinned_blueprint_carries_the_reference_fields(self):
        """The content classes and the pinned definitions agree on which natives may hold a stored value, and on its value field."""
        for native_code in NativeConceptCode:
            structure = make_pinned_native_blueprint(native_code).structure
            carries_reference = isinstance(structure, dict) and set(STORED_VALUE_REFERENCE_FIELDS) <= set(structure)
            structure_class = native_code.structure_class
            if structure_class is None or not issubclass(structure_class, StoredValueContent):
                assert not carries_reference, native_code
                continue
            assert carries_reference, native_code
            assert isinstance(structure, dict)
            assert structure_class.value_field_name in structure, native_code
