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
    """Register test concepts for the module.

    This fixture:
    1. Registers test structure classes in the class registry
    2. Creates and registers test concepts in the concept provider
    3. Yields to run tests
    4. Cleans up by removing test concepts from the provider

    The cleanup ensures test isolation between modules.
    """
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

    # GalleryWithImageList concept
    gallery_list_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="GalleryWithImageList",
        description="A gallery with a list of images",
        structure_class_name="GalleryWithImageList",
    )
    concepts_to_register.append(gallery_list_concept)

    # PersonWithImageTuple concept
    person_tuple_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="PersonWithImageTuple",
        description="A person with a tuple of images",
        structure_class_name="PersonWithImageTuple",
    )
    concepts_to_register.append(person_tuple_concept)

    # PhotoAlbumItem concept
    album_item_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="PhotoAlbumItem",
        description="An item in a photo album",
        structure_class_name="PhotoAlbumItem",
    )
    concepts_to_register.append(album_item_concept)

    # PhotoAlbumWithNestedImages concept
    album_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="PhotoAlbumWithNestedImages",
        description="A photo album with nested images in list items",
        structure_class_name="PhotoAlbumWithNestedImages",
    )
    concepts_to_register.append(album_concept)

    # MediaFrame concept
    media_frame_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="MediaFrame",
        description="A frame containing an image",
        structure_class_name="MediaFrame",
    )
    concepts_to_register.append(media_frame_concept)

    # MediaSection concept
    media_section_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="MediaSection",
        description="A section with multiple frames",
        structure_class_name="MediaSection",
    )
    concepts_to_register.append(media_section_concept)

    # MediaCollection concept
    media_collection_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="MediaCollection",
        description="A collection with sections and thumbnails",
        structure_class_name="MediaCollection",
    )
    concepts_to_register.append(media_collection_concept)

    # ComplexNestedGallery concept
    complex_gallery_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="ComplexNestedGallery",
        description="A deeply nested gallery structure",
        structure_class_name="ComplexNestedGallery",
    )
    concepts_to_register.append(complex_gallery_concept)

    # GalleryWithListContent concept
    list_content_gallery_concept = ConceptFactory.make(
        domain=TestData.DOMAIN,
        concept_code="GalleryWithListContent",
        description="A gallery using ListContent",
        structure_class_name="GalleryWithListContent",
    )
    concepts_to_register.append(list_content_gallery_concept)

    # Add all concepts to the provider
    concept_provider.add_concepts(concepts_to_register)

    # Yield to run tests
    yield

    # Cleanup: Remove test concepts from provider
    concept_strings = [concept.concept_string for concept in concepts_to_register]
    concept_provider.remove_concepts_by_codes(concept_strings)


class TestConceptFindImageFieldPaths:
    """Test Concept.search_for_nested_image_fields_in_structure_class() method."""

    @pytest.mark.parametrize(
        ("concept_code", "expected_paths"),
        TestData.IMAGE_FIELD_TEST_CASES,
        ids=[case[0] for case in TestData.IMAGE_FIELD_TEST_CASES],
    )
    def test_find_image_fields(self, concept_code: str, expected_paths: list[str]):
        """Test finding image fields in various structure classes.

        This parametrized test covers:
        - Direct image fields
        - Refined image fields (concepts that refine Image)
        - No image fields
        - Nested image fields at various depths
        - Multiple image fields at different levels
        - Optional image fields
        - Lists of images
        - Tuples of images
        - Lists with nested structures containing images
        - Complex deeply nested structures
        - ListContent with nested images

        Args:
            concept_code: The code of the concept to test
            expected_paths: The expected list of image field paths
        """
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.{concept_code}")

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert exact match of paths (order-independent)
        assert sorted(image_paths) == sorted(expected_paths), f"Expected paths {sorted(expected_paths)}, but got {sorted(image_paths)}"

    def test_direct_image_concept(self):
        """Test with a concept that is directly an Image.

        The native Image concept itself should return empty paths because
        the concept is an image, not a structured type with image fields.
        """
        # Get concept
        concept = get_native_concept(NativeConceptEnum.IMAGE)

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert - should return empty because the concept itself is an image
        assert image_paths == []

    def test_native_text_and_images_content(self):
        """Test the native TextAndImagesContent which has list[ImageContent] | None.

        This tests the native concept that combines text and images.
        """
        # Get the native TextAndImages concept
        concept = get_native_concept(NativeConceptEnum.TEXT_AND_IMAGES)

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert - should find the images field which is list[ImageContent] | None
        assert image_paths == ["images"]
