import pytest
from kajson.kajson_manager import KajsonManager
from pydantic import ValidationError

from pipelex.cogt.image.image_size import ImageSize
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.exceptions import ConceptStringError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.native.exceptions import NativeConceptDefinitionError
from pipelex.core.concepts.validation import validate_concept_ref
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.stuffs.structured_content import StructuredContent


# Custom StuffContent class with nested ImageContent-like field for testing
class NestedImageInfo(StructuredContent):
    """A nested structure that contains image-like data (same structure as ImageContent)."""

    url: str
    public_url: str | None = None
    source_prompt: str | None = None
    source_negative_prompt: str | None = None
    caption: str | None = None
    mime_type: str | None = None
    size: ImageSize | None = None
    filename: str | None = None


class DocumentWithNestedImage(StructuredContent):
    """A content class that has a nested field containing image info."""

    title: str
    metadata: NestedImageInfo


class TestConcept:
    """Test Concept class."""

    def test_get_validated_native_concept_ref(self):
        assert NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.TEXT) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"
        assert NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.IMAGE) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.IMAGE}"
        assert (
            NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.DOCUMENT) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.DOCUMENT}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.TEXT_AND_IMAGES)
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT_AND_IMAGES}"
        )
        assert NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.NUMBER) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.NUMBER}"
        assert (
            NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.ANYTHING) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.ANYTHING}"
        )
        assert NativeConceptCode.get_validated_native_concept_ref(NativeConceptCode.DYNAMIC) == f"{SpecialDomain.NATIVE}.{NativeConceptCode.DYNAMIC}"
        assert (
            NativeConceptCode.get_validated_native_concept_ref(f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_ref(f"{SpecialDomain.NATIVE}.{NativeConceptCode.IMAGE}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.IMAGE}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_ref(f"{SpecialDomain.NATIVE}.{NativeConceptCode.DOCUMENT}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.DOCUMENT}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_ref(f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT_AND_IMAGES}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT_AND_IMAGES}"
        )
        assert (
            NativeConceptCode.get_validated_native_concept_ref(f"{SpecialDomain.NATIVE}.{NativeConceptCode.NUMBER}")
            == f"{SpecialDomain.NATIVE}.{NativeConceptCode.NUMBER}"
        )
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.TEXT}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.IMAGE}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.DOCUMENT}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.TEXT_AND_IMAGES}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.NUMBER}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.ANYTHING}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref(f"not_native.{NativeConceptCode.DYNAMIC}")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref("RandomConcept")
        with pytest.raises(NativeConceptDefinitionError):
            NativeConceptCode.get_validated_native_concept_ref("text")

    def test_is_native_concept(self):
        """Test is_native_concept method."""
        valid_domain = "valid_domain"
        valid_definition = "Lorem Ipsum"

        for native_concept_code in NativeConceptCode.values_list():
            native_concept = ConceptFactory.make_native_concept(native_concept_code=native_concept_code)
            assert Concept.is_native_concept(native_concept) is True

        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.TEXT,
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.TEXT,
                    domain_code=SpecialDomain.NATIVE,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.IMAGE,
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.DOCUMENT,
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.TEXT_AND_IMAGES,
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.NUMBER,
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code=NativeConceptCode.ANYTHING,
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is True
        )
        assert (
            Concept.is_native_concept(
                ConceptFactory.make_from_blueprint(
                    concept_code="RandomConcept",
                    domain_code=valid_domain,
                    blueprint_or_string_description=ConceptBlueprint(description=valid_definition),
                ),
            )
            is False
        )

    def test_construct_concept_ref_with_domain(self):
        """Test construct_concept_ref_with_domain method."""
        valid_domain = "valid_domain"
        assert (
            ConceptFactory.make_concept_ref_with_domain(domain_code=valid_domain, concept_code=NativeConceptCode.TEXT)
            == f"{valid_domain}.{NativeConceptCode.TEXT}"
        )

    def test_validate_concept_ref(self):
        """Test validate_concept_ref method."""
        valid_domain = "valid_domain"
        valid_concept_code = "ConceptCode"
        valid_concept_ref = f"{valid_domain}.{valid_concept_code}"
        # Valid cases - should not raise exceptions
        validate_concept_ref(valid_concept_ref)
        validate_concept_ref(f"domain_123.{valid_concept_code}")
        validate_concept_ref(f"{SpecialDomain.NATIVE}.{NativeConceptCode.ANYTHING}")
        validate_concept_ref(f"{valid_domain}.UPPERCASE")

        # Invalid cases - should raise ConceptCodeError
        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"snake_case_domaiN.{valid_concept_code}")

        # Hierarchical domains (multiple dots) - now valid
        validate_concept_ref(f"domain.sub.{valid_concept_code}")
        validate_concept_ref(f"a.b.c.{valid_concept_code}")

        # Invalid domain (not snake_case)
        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"InvalidDomain.{valid_concept_code}")

        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"domain-name.{valid_concept_code}")

        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"Domain_Name.{valid_concept_code}")

        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"123domain.{valid_concept_code}")

        # Invalid concept code (not PascalCase)
        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"{valid_domain}.invalidText")

        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"{valid_domain}.text")

        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"{valid_domain}.Text_Name")

        with pytest.raises(ConceptStringError):
            validate_concept_ref(f"{valid_domain}.text-name")

    @pytest.mark.parametrize(
        "domain_code",
        [
            "scoring_lib->scoring",
            "my_lib->legal.contracts",
        ],
    )
    def test_concept_with_cross_package_domain_code(self, domain_code: str):
        """Concept construction with a cross-package domain code should pass validation."""
        concept = Concept(
            code="WeightedScore",
            domain_code=domain_code,
            description="Test concept",
            structure_class_name="TextContent",
        )
        assert concept.domain_code == domain_code

    @pytest.mark.parametrize(
        "domain_code",
        [
            "lib->",
            "lib->Legal",
            "lib->.scoring",
        ],
    )
    def test_concept_with_invalid_cross_package_domain_code(self, domain_code: str):
        """Concept construction with an invalid cross-package domain code should raise."""
        with pytest.raises(ValidationError):
            Concept(
                code="WeightedScore",
                domain_code=domain_code,
                description="Test concept",
                structure_class_name="TextContent",
            )

    def test_are_concept_compatible(self):
        concept1 = ConceptFactory.make_from_blueprint(
            concept_code="Code1",
            domain_code="domain1",
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum", refines=NativeConceptCode.TEXT),
        )
        concept2 = ConceptFactory.make_from_blueprint(
            concept_code="Code2",
            domain_code="domain1",
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum", refines=NativeConceptCode.TEXT),
        )
        concept3 = ConceptFactory.make_from_blueprint(
            concept_code="Code3",
            domain_code="domain2",
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum", structure="TextContent"),
        )
        concept4 = ConceptFactory.make_from_blueprint(
            concept_code="Code4",
            domain_code="domain1",
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum", structure="ImageContent"),
        )

        concept_5 = ConceptFactory.make_native_concept(
            native_concept_code=NativeConceptCode.PAGE,
        )

        concept_6 = ConceptFactory.make_native_concept(
            native_concept_code=NativeConceptCode.IMAGE,
        )

        concept_7 = ConceptFactory.make_from_blueprint(
            concept_code="VisualDescription",
            domain_code="images",
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum"),
        )

        assert Concept.are_concept_compatible(concept_7, concept_6, strict=True) is False
        assert Concept.are_concept_compatible(concept_7, concept_6, strict=False) is False

        # Test same code and domain
        assert Concept.are_concept_compatible(concept1, concept2) is True

        # Test different code and domain
        assert Concept.are_concept_compatible(concept1, concept3) is True

        # Test same structure class name
        assert Concept.are_concept_compatible(concept1, concept4) is False

        # Test same refines
        assert Concept.are_concept_compatible(concept_5, concept_6, strict=False) is True
        assert Concept.are_concept_compatible(concept_5, concept_6, strict=True) is False

    def test_concept_refining_text_is_strictly_compatible(self):
        """Test that a concept created with .make() that refines native.Text is strictly compatible with Text."""
        # Create a concept that refines native.Text using ConceptFactory.make()
        concept_not_native_text = ConceptFactory.make(
            domain_code="test_domain",
            concept_code="MyConceptNotNativeText",
            description="Test concept for unit tests",
            structure_class_name="TextContent",
            refines="native.Text",
        )

        # Get the native Text concept
        text_concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)

        # A concept that refines Text should be strictly compatible with Text
        assert Concept.are_concept_compatible(concept_not_native_text, text_concept, strict=True) is True
        assert Concept.are_concept_compatible(concept_not_native_text, text_concept, strict=False) is True

    def test_concept_with_same_structure_as_text_content(self):
        """Test: create a concept with a structure EXACTLY like TextContent (text: str) and compare with native Text."""
        # Create a concept with a structure blueprint that has exactly the same field as TextContent: text: str
        custom_text_like_concept = ConceptFactory.make_from_blueprint(
            concept_code="MyTextLikeConcept",
            domain_code="test_structure_equiv",
            blueprint_or_string_description=ConceptBlueprint(
                description="A concept with the exact same structure as TextContent",
                structure={
                    "text": ConceptStructureBlueprint(
                        type=ConceptStructureBlueprintFieldType.TEXT,
                        description="The text content",
                        required=True,
                    ),
                },
            ),
        )

        # Get the native Text concept
        native_text_concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)

        # They have different structure_class_names but the same JSON structure
        assert custom_text_like_concept.structure_class_name != native_text_concept.structure_class_name

        # Concepts with the same JSON structure should be compatible
        assert Concept.are_concept_compatible(custom_text_like_concept, native_text_concept, strict=True) is True
        assert Concept.are_concept_compatible(custom_text_like_concept, native_text_concept, strict=False) is True

    def test_nested_image_content_strict_false_nonstrict_true(self):
        """Test: strict=True returns False, strict=False returns True for nested compatible field."""
        # Register our custom classes with the class registry
        KajsonManager.get_class_registry().register_class(NestedImageInfo)
        KajsonManager.get_class_registry().register_class(DocumentWithNestedImage)

        # Create a concept using our custom DocumentWithNestedImage class
        concept_with_nested_image = ConceptFactory.make(
            domain_code="test_nested",
            concept_code="DocumentWithImage",
            description="A document containing nested image info",
            structure_class_name="DocumentWithNestedImage",
        )

        # Create a concept using the NestedImageInfo class (same structure as ImageContent)
        concept_image_like = ConceptFactory.make(
            domain_code="test_nested",
            concept_code="ImageInfo",
            description="Image-like info",
            structure_class_name="NestedImageInfo",
        )

        # Get the native Image concept (uses ImageContent)
        native_image_concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE)

        # --- Test with NestedImageInfo (custom class with same structure as ImageContent) ---
        # strict=True should be False: DocumentWithNestedImage is NOT structurally equivalent to NestedImageInfo
        assert Concept.are_concept_compatible(concept_with_nested_image, concept_image_like, strict=True) is False
        # strict=False should be True: DocumentWithNestedImage has a field (metadata) that is NestedImageInfo
        assert Concept.are_concept_compatible(concept_with_nested_image, concept_image_like, strict=False) is True

        # --- Test NestedImageInfo vs native Image (ImageContent) ---
        # NestedImageInfo has the same structure as ImageContent, so should be strictly compatible
        assert Concept.are_concept_compatible(concept_image_like, native_image_concept, strict=True) is True
        assert Concept.are_concept_compatible(concept_image_like, native_image_concept, strict=False) is True

        # --- Test DocumentWithNestedImage vs native Image (ImageContent) ---
        # strict=True should be False: DocumentWithNestedImage is NOT structurally equivalent to ImageContent
        assert Concept.are_concept_compatible(concept_with_nested_image, native_image_concept, strict=True) is False
        # strict=False should be True: DocumentWithNestedImage has a nested field (metadata: NestedImageInfo)
        # that is STRUCTURALLY EQUIVALENT to ImageContent
        assert Concept.are_concept_compatible(concept_with_nested_image, native_image_concept, strict=False) is True
