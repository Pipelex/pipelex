from pipelex.codegen.native_expansion import materialize_native_concept
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode


class TestNativeExpansion:
    """Materializing native content classes into explicit concept blueprints."""

    def test_image_materializes_with_structure_and_nested_model_as_dict(self):
        """`Image` maps every field; the nested non-native `ImageSize` model maps to a dict blueprint
        (its wire form is a JSON object) instead of making the whole native structureless.
        """
        blueprint = materialize_native_concept(NativeConceptCode.IMAGE)
        assert isinstance(blueprint.structure, dict)
        assert {"url", "public_url", "mime_type", "caption", "size"} <= set(blueprint.structure.keys())
        url_field = blueprint.structure["url"]
        assert isinstance(url_field, ConceptStructureBlueprint)
        assert url_field.type == ConceptStructureBlueprintFieldType.TEXT
        assert url_field.required is True
        size_field = blueprint.structure["size"]
        assert isinstance(size_field, ConceptStructureBlueprint)
        assert size_field.type == ConceptStructureBlueprintFieldType.DICT
        assert size_field.required is False

    def test_document_materializes_with_full_structure(self):
        blueprint = materialize_native_concept(NativeConceptCode.DOCUMENT)
        assert isinstance(blueprint.structure, dict)
        assert {"url", "public_url", "mime_type", "filename", "title", "snippet"} == set(blueprint.structure.keys())

    def test_unmappable_content_class_stays_structureless(self):
        """A native whose content class has no honest blueprint form materializes structureless
        (declared imprecision), never a guessed shape.
        """
        blueprint = materialize_native_concept(NativeConceptCode.DATE)
        assert blueprint.structure is None
        assert blueprint.description
