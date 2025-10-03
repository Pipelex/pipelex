import pytest

from pipelex.core.concepts.concept import Concept  # noqa: TC001
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.hub import get_concept_provider, get_native_concept
from pipelex.tools.class_registry_utils import ClassRegistryUtils
from tests.unit.pipelex.core.concepts import data
from tests.unit.pipelex.core.concepts.data import TestData


@pytest.fixture(scope="module", autouse=True)
def register_test_concepts():
    """Register test concepts for the module."""
    concept_provider = get_concept_provider()

    # Register the test structure classes
    ClassRegistryUtils.register_classes_in_file(
        file_path=data.__file__,
        base_class=StructuredContent,
        is_include_imported=False,
    )

    # Create and register concepts
    concepts_to_register: list[Concept] = []

    # ProfilePhoto concept that refines Image
    profile_photo_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="ProfilePhoto",
        description="A profile photo",
        structure_class_name="ProfilePhoto",
        refines=f"native.{NativeConceptEnum.IMAGE}",
    )
    concepts_to_register.append(profile_photo_concept)

    # PersonWithDirectImage concept
    person_direct_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="PersonWithDirectImage",
        description="A person with a direct image field",
        structure_class_name="PersonWithDirectImage",
    )
    concepts_to_register.append(person_direct_concept)

    # PersonWithRefinedImage concept
    person_refined_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="PersonWithRefinedImage",
        description="A person with a refined image field",
        structure_class_name="PersonWithRefinedImage",
    )
    concepts_to_register.append(person_refined_concept)

    # PersonWithText concept
    person_text_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="PersonWithText",
        description="A person with only text",
        structure_class_name="PersonWithText",
    )
    concepts_to_register.append(person_text_concept)

    # CompanyInfo concept
    company_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="CompanyInfo",
        description="Company information",
        structure_class_name="CompanyInfo",
    )
    concepts_to_register.append(company_concept)

    # NestedComplex concept
    nested_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="NestedComplex",
        description="Complex nested structure",
        structure_class_name="NestedComplex",
    )
    concepts_to_register.append(nested_concept)

    # PersonWithOptionalImage concept
    person_optional_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="PersonWithOptionalImage",
        description="A person with optional image",
        structure_class_name="PersonWithOptionalImage",
    )
    concepts_to_register.append(person_optional_concept)

    # Add all concepts to the provider
    concept_provider.add_concepts(concepts_to_register)

    # Cleanup after tests (optional)


class TestConceptFindImageFieldPaths:
    """Test ConceptLibrary.find_image_field_paths() method."""

    def test_direct_image_field(self):
        """Test finding a direct image field."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.PersonWithDirectImage")

        # Find image paths
        image_paths = get_concept_provider().find_image_field_paths(concept=concept)

        # Assert
        assert len(image_paths) == 1
        assert "photo" in image_paths

    def test_refined_image_field(self):
        """Test finding an image field that uses a concept refining Image."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.PersonWithRefinedImage")

        # Find image paths
        image_paths = get_concept_provider().find_image_field_paths(concept=concept)

        # Assert
        assert len(image_paths) == 1
        assert "profile_photo" in image_paths

    def test_no_image_fields(self):
        """Test with content that has no image fields."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.PersonWithText")

        # Find image paths
        image_paths = get_concept_provider().find_image_field_paths(concept=concept)

        # Assert
        assert len(image_paths) == 0

    def test_nested_image_field(self):
        """Test finding image fields in nested structures."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.CompanyInfo")

        # Find image paths
        image_paths = get_concept_provider().find_image_field_paths(concept=concept)

        # Assert
        assert len(image_paths) == 1
        assert "ceo.photo" in image_paths

    def test_multiple_nested_levels_with_multiple_images(self):
        """Test finding multiple image fields at different nesting levels."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.NestedComplex")

        # Find image paths
        image_paths = get_concept_provider().find_image_field_paths(concept=concept)

        # Assert - should find both the logo and the nested CEO photo
        assert len(image_paths) == 2
        assert "logo" in image_paths
        assert "company.ceo.photo" in image_paths

    def test_optional_image_field_with_value(self):
        """Test finding an optional image field that has a value."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.PersonWithOptionalImage")

        # Find image paths
        image_paths = get_concept_provider().find_image_field_paths(concept=concept)

        # Assert
        assert len(image_paths) == 1
        assert "photo" in image_paths

    def test_optional_image_field_without_value(self):
        """Test finding an optional image field that is None.

        Note: Since find_image_field_paths() works at the concept/class level (not instance level),
        it returns all fields typed as Images, regardless of whether they have values in a specific instance.
        """
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.PersonWithOptionalImage")

        # Find image paths
        image_paths = get_concept_provider().find_image_field_paths(concept=concept)

        # Assert - should find the photo field even though it's None in this instance
        # because we're analyzing the class structure, not instance values
        assert len(image_paths) == 1
        assert "photo" in image_paths

    def test_direct_image_concept(self):
        """Test with a concept that is directly an Image."""
        # Get concept
        concept = get_native_concept(NativeConceptEnum.IMAGE)

        # Find image paths
        image_paths = get_concept_provider().find_image_field_paths(concept=concept)

        # Assert - should return empty because the concept itself is an image, not a structured type with image fields
        assert len(image_paths) == 0
