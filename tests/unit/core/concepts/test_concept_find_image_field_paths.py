from typing import TYPE_CHECKING

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.hub import get_concept_library, get_native_concept, get_required_concept
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from tests.unit.core.concepts import data
from tests.unit.core.concepts.data import TestData

if TYPE_CHECKING:
    from pipelex.core.concepts.concept import Concept


@pytest.fixture(scope="module", autouse=True)
def register_test_concepts():
    """Register test concepts for the module.

    This fixture:
    1. Registers test structure classes in the class registry
    2. Creates and registers test concepts in the concept library
    3. Yields to run tests
    4. Cleans up by removing test concepts from the library

    The cleanup ensures test isolation between modules.
    """
    concept_library = get_concept_library()

    # Register the test structure classes
    ClassRegistryUtils.register_classes_in_file(
        file_path=data.__file__,
        base_class=StructuredContent,
        is_include_imported=False,
    )

    # Define concept specifications: (code, description, structure_class_name, refines)
    concept_specs: list[tuple[str, str, str, str | None]] = [
        ("ProfilePhoto", "A profile photo", "ProfilePhoto", f"native.{NativeConceptCode.IMAGE}"),
        ("PersonWithDirectImage", "A person with a direct image field", "PersonWithDirectImage", None),
        ("PersonWithRefinedImage", "A person with a refined image field", "PersonWithRefinedImage", None),
        ("PersonWithText", "A person with only text", "PersonWithText", None),
        ("CompanyInfo", "Company information", "CompanyInfo", None),
        ("NestedComplex", "Complex nested structure", "NestedComplex", None),
        ("PersonWithOptionalImage", "A person with optional image", "PersonWithOptionalImage", None),
        ("GalleryWithImageList", "A gallery with a list of images", "GalleryWithImageList", None),
        ("PersonWithImageTuple", "A person with a tuple of images", "PersonWithImageTuple", None),
        ("PhotoAlbumItem", "An item in a photo album", "PhotoAlbumItem", None),
        ("PhotoAlbumWithNestedImages", "A photo album with nested images in list items", "PhotoAlbumWithNestedImages", None),
        ("MediaFrame", "A frame containing an image", "MediaFrame", None),
        ("MediaSection", "A section with multiple frames", "MediaSection", None),
        ("MediaCollection", "A collection with sections and thumbnails", "MediaCollection", None),
        ("ComplexNestedGallery", "A deeply nested gallery structure", "ComplexNestedGallery", None),
        ("GalleryWithListContent", "A gallery using ListContent", "GalleryWithListContent", None),
    ]

    # Create and register concepts
    concepts_to_register: list[Concept] = [
        ConceptFactory.make(
            domain=TestData.DOMAIN,
            concept_code=code,
            description=description,
            structure_class_name=structure_class_name,
            refines=refines,
        )
        for code, description, structure_class_name, refines in concept_specs
    ]

    # Add all concepts to the library
    concept_library.add_concepts(concepts_to_register)

    # Yield to run tests
    yield

    # Cleanup: Remove test concepts from library
    concept_strings = [concept.concept_string for concept in concepts_to_register]
    concept_library.remove_concepts_by_concept_strings(concept_strings)


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
        concept = get_required_concept(f"{TestData.DOMAIN}.{concept_code}")

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
        concept = get_native_concept(NativeConceptCode.IMAGE)

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert - should return empty because the concept itself is an image
        assert image_paths == []

    def test_native_text_and_images_content(self):
        """Test the native TextAndImagesContent which has list[ImageContent] | None.

        This tests the native concept that combines text and images.
        """
        # Get the native TextAndImages concept
        concept = get_native_concept(NativeConceptCode.TEXT_AND_IMAGES)

        # Find image paths
        image_paths = concept.search_for_nested_image_fields_in_structure_class()

        # Assert - should find the images field which is list[ImageContent] | None
        assert image_paths == ["images"]
