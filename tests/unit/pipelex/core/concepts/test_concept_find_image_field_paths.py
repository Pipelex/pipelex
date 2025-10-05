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

    # Cleanup after tests (optional)


class TestConceptFindImageFieldPaths:
    """Test Concept.find_nested_image_fields_in_structure_class() method."""

    def test_direct_image_field(self):
        """Test finding a direct image field."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.PersonWithDirectImage")

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert
        assert len(image_paths) == 1
        assert "photo" in image_paths

    def test_refined_image_field(self):
        """Test finding an image field that uses a concept refining Image."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.PersonWithRefinedImage")

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert
        assert len(image_paths) == 1
        assert "profile_photo" in image_paths

    def test_no_image_fields(self):
        """Test with content that has no image fields."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.PersonWithText")

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert
        assert len(image_paths) == 0

    def test_nested_image_field(self):
        """Test finding image fields in nested structures."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.CompanyInfo")

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert
        assert len(image_paths) == 1
        assert "ceo.photo" in image_paths

    def test_multiple_nested_levels_with_multiple_images(self):
        """Test finding multiple image fields at different nesting levels."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.NestedComplex")

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert - should find both the logo and the nested CEO photo
        assert len(image_paths) == 2
        assert "logo" in image_paths
        assert "company.ceo.photo" in image_paths

    def test_optional_image_field_with_value(self):
        """Test finding an optional image field that has a value."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.PersonWithOptionalImage")

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert
        assert len(image_paths) == 1
        assert "photo" in image_paths

    def test_optional_image_field_without_value(self):
        """Test finding an optional image field that is None.

        Note: Since find_nested_image_fields_in_structure_class() works at the concept/class level (not instance level),
        it returns all fields typed as Images, regardless of whether they have values in a specific instance.
        """
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.PersonWithOptionalImage")

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert - should find the photo field even though it's None in this instance
        # because we're analyzing the class structure, not instance values
        assert len(image_paths) == 1
        assert "photo" in image_paths

    def test_direct_image_concept(self):
        """Test with a concept that is directly an Image."""
        # Get concept
        concept = get_native_concept(NativeConceptEnum.IMAGE)

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert - should return empty because the concept itself is an image, not a structured type with image fields
        assert len(image_paths) == 0

    def test_list_of_images(self):
        """Test finding a field that is a list of images."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.GalleryWithImageList")

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert - should find the photos field which contains a list of images
        assert len(image_paths) == 1
        assert "photos" in image_paths

    def test_tuple_of_images(self):
        """Test finding a field that is a tuple of images."""
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.PersonWithImageTuple")

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert - should find the before_after field which contains a tuple of images
        assert len(image_paths) == 1
        assert "before_after" in image_paths

    def test_native_text_and_images_content(self):
        """Test the native TextAndImagesContent which has list[ImageContent] | None."""
        # Get the native TextAndImages concept
        concept = get_native_concept(NativeConceptEnum.TEXT_AND_IMAGES)

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert - should find the images field which is list[ImageContent] | None
        assert len(image_paths) == 1
        assert "images" in image_paths

    def test_list_with_nested_images(self):
        """Test finding images nested inside structures within a list.

        This tests the recursive detection: list[PhotoAlbumItem] where PhotoAlbumItem has an ImageContent field.
        """
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.PhotoAlbumWithNestedImages")

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert - should find album_items because PhotoAlbumItem contains an ImageContent
        assert len(image_paths) == 1
        assert "album_items" in image_paths

    def test_complex_deeply_nested_images(self):
        """Test finding images in a deeply nested, complex structure.

        Structure being tested: list[tuple[MediaCollection, list[PhotoAlbumItem]]]

        This tests multiple levels of nesting:
        - Level 1: list container
        - Level 2: tuple with two items
        - Level 3a: MediaCollection (has direct 'thumbnail' + nested 'sections')
        - Level 4a: sections -> list[MediaSection]
        - Level 5a: MediaSection.frames -> list[MediaFrame]
        - Level 6a: MediaFrame.frame_image -> ImageContent
        - Level 3b: list[PhotoAlbumItem]
        - Level 4b: PhotoAlbumItem.photo -> ImageContent

        The field should be detected because both tuple items contain images at various nesting levels.
        """
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.ComplexNestedGallery")

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert - should find gallery_entries because:
        # 1. MediaCollection has 'thumbnail' (direct) and 'sections->frames->frame_image' (nested)
        # 2. list[PhotoAlbumItem] has nested 'photo' field
        assert len(image_paths) == 1
        assert "gallery_entries" in image_paths

    def test_list_content_with_nested_images(self):
        """Test finding images in ListContent items.

        Structure being tested: ListContent[PhotoAlbumItem]

        This tests that ListContent is not skipped, and that we check its generic argument
        to see if the items (PhotoAlbumItem) contain images.
        """
        # Get concept
        concept = get_concept_provider().get_required_concept(f"{TestData.DOMAIN}.GalleryWithListContent")

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert - should find album_list because PhotoAlbumItem contains an ImageContent
        assert len(image_paths) == 1
        assert "album_list" in image_paths
