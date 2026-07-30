"""Integration tests for inline structure definitions in concepts."""

import pytest

from pipelex.core.concepts.concept_blueprint import (
    ConceptBlueprint,
    ConceptStructureBlueprint,
)
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprintFieldType
from pipelex.core.concepts.exceptions import ConceptFactoryError
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.runtime_hub import get_class_registry


class TestInlineStructureConcepts:
    """Test inline structure definitions in concept blueprints."""

    def test_inline_structure_definition_creation(self):
        """Test that concepts with inline structure definitions are created correctly."""
        # Define inline structure with mixed syntax
        inline_structure: dict[str, str | ConceptStructureBlueprint] = {
            "dominant_feature": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description="The most important feature",
                required=False,
            ),
            "visual_elements": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description="Key visual elements",
                required=False,
            ),
            "composition": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description="Analysis of the image composition",
                required=False,
            ),
            "color_palette": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description="Description of the main colors",
                required=False,
            ),
            "mood_atmosphere": "The overall mood or atmosphere",
        }

        # Create concept blueprint with inline structure
        blueprint = ConceptBlueprint(description="Analysis of a photo's visual content", structure=inline_structure)

        # Create concept from blueprint
        concept = ConceptFactory.make_from_blueprint(
            domain_code="test_domain",
            concept_code="TestFeatureAnalysis",
            blueprint_or_string_description=blueprint,
        )

        # Verify concept properties
        assert concept.domain_code == "test_domain"
        assert concept.code == "TestFeatureAnalysis"
        assert concept.description == "Analysis of a photo's visual content"
        assert concept.structure_class_name == "test_domain__TestFeatureAnalysis"

        # Verify the generated class is registered and accessible
        assert get_class_registry().has_class("test_domain__TestFeatureAnalysis")
        generated_class = get_class_registry().get_required_subclass("test_domain__TestFeatureAnalysis", StructuredContent)

        # Verify class structure
        assert issubclass(generated_class, StructuredContent)
        assert generated_class.__name__ == "test_domain__TestFeatureAnalysis"

        # Test instantiation of generated class
        instance = generated_class(
            dominant_feature="A bright red car",  # pyright: ignore[reportCallIssue]
            visual_elements="Car, road, trees, sky",  # pyright: ignore[reportCallIssue]
            composition="Central composition with car in focus",  # pyright: ignore[reportCallIssue]
            color_palette="Red, green, blue, white",  # pyright: ignore[reportCallIssue]
            mood_atmosphere="The overall mood or atmosphere",  # pyright: ignore[reportCallIssue]
        )

        assert instance.dominant_feature == "A bright red car"  # type: ignore[attr-defined] # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
        assert instance.visual_elements == "Car, road, trees, sky"  # type: ignore[attr-defined] # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
        assert instance.composition == "Central composition with car in focus"  # type: ignore[attr-defined] # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
        assert instance.color_palette == "Red, green, blue, white"  # type: ignore[attr-defined] # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]

    def test_string_reference_structure_definition(self):
        """Test that string reference structure definitions still work."""
        # Create blueprint with string reference
        blueprint = ConceptBlueprint(description="Test with string reference", structure="TextContent")

        # Create concept from blueprint
        concept = ConceptFactory.make_from_blueprint(
            domain_code="test_domain",
            concept_code="TestStringRef",
            blueprint_or_string_description=blueprint,
        )

        # Verify concept properties
        assert concept.code == "TestStringRef"
        assert concept.domain_code == "test_domain"
        assert concept.description == "Test with string reference"
        assert concept.structure_class_name == "TextContent"

    def test_auto_detection_structure(self):
        """Test auto-detection when no structure is specified."""
        # Create blueprint without structure
        blueprint = ConceptBlueprint(description="Test auto-detection")

        # Create concept from blueprint
        concept = ConceptFactory.make_from_blueprint(
            domain_code="test_domain",
            concept_code="TestAutoDetect",
            blueprint_or_string_description=blueprint,
        )

        # Should default to TextContent since TestAutoDetect is not a registered class
        assert concept.structure_class_name == "test_domain__TestAutoDetect"
        assert concept.refines == "native.Text"

    def test_inline_structure_with_complex_types(self):
        """Test inline structure with complex field types."""
        inline_structure: dict[str, str | ConceptStructureBlueprint] = {
            "title": ConceptStructureBlueprint(type=ConceptStructureBlueprintFieldType.TEXT, description="Document title"),
            "tags": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.LIST,
                item_type=ConceptStructureBlueprintFieldType.TEXT,
                description="List of tags",
                required=False,
            ),
            "metadata": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.DICT,
                key_type=ConceptStructureBlueprintFieldType.TEXT,
                value_type=ConceptStructureBlueprintFieldType.TEXT,
                description="Metadata dictionary",
                required=False,
            ),
            "priority": ConceptStructureBlueprint(choices=["low", "medium", "high"], description="Priority level", required=False),
            "page_count": ConceptStructureBlueprint(type=ConceptStructureBlueprintFieldType.INTEGER, description="Number of pages", required=False),
            "is_active": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.BOOLEAN,
                description="Whether document is active",
                required=False,
            ),
        }

        blueprint = ConceptBlueprint(description="Complex document structure", structure=inline_structure)

        concept = ConceptFactory.make_from_blueprint(
            domain_code="test_domain",
            concept_code="ComplexDocument",
            blueprint_or_string_description=blueprint,
        )

        # Verify concept creation
        assert concept.code == "ComplexDocument"
        assert concept.domain_code == "test_domain"
        assert concept.structure_class_name == "test_domain__ComplexDocument"

        # Verify the generated class works
        generated_class = get_class_registry().get_required_subclass("test_domain__ComplexDocument", StructuredContent)

        # Test instantiation with complex types
        instance = generated_class(
            title="Test Document",
            tags=["test", "document"],
            metadata={"author": "Test Author", "version": "1.0"},
            priority="high",
            page_count=42,
            is_active=True,
        )

        assert instance.title == "Test Document"
        assert instance.tags == ["test", "document"]
        assert instance.metadata == {"author": "Test Author", "version": "1.0"}
        assert instance.priority == "high"
        assert instance.page_count == 42
        assert instance.is_active is True

    def test_invalid_string_reference_raises_error(self):
        """Test that invalid string references raise appropriate errors."""
        with pytest.raises(
            ConceptFactoryError,
            match="Structure class 'NonExistentClass' set for concept 'TestInvalidRef' in domain 'test_domain' is \
not a registered subclass of StuffContent",
        ):
            _ = ConceptFactory.make_from_blueprint(
                domain_code="test_domain",
                concept_code="TestInvalidRef",
                blueprint_or_string_description=ConceptBlueprint(description="Test invalid reference", structure="NonExistentClass"),
            )

    def test_multiple_inline_structures_do_not_conflict(self):
        """Test that multiple inline structures with same field names don't conflict."""
        # First structure
        structure1: dict[str, str | ConceptStructureBlueprint] = {
            "name": ConceptStructureBlueprint(type=ConceptStructureBlueprintFieldType.TEXT, description="Person name"),
            "age": ConceptStructureBlueprint(type=ConceptStructureBlueprintFieldType.INTEGER, description="Person age", required=False),
        }

        blueprint1 = ConceptBlueprint(description="Person information", structure=structure1)
        concept1 = ConceptFactory.make_from_blueprint(
            domain_code="test_domain",
            concept_code="Person",
            blueprint_or_string_description=blueprint1,
        )

        # Second structure with same field names but different context
        structure2: dict[str, str | ConceptStructureBlueprint] = {
            "name": "Product name",
            "age": ConceptStructureBlueprint(type=ConceptStructureBlueprintFieldType.INTEGER, description="Product age in days", required=False),
        }

        blueprint2 = ConceptBlueprint(description="Product information", structure=structure2)
        concept2 = ConceptFactory.make_from_blueprint(
            domain_code="test_domain",
            concept_code="Product",
            blueprint_or_string_description=blueprint2,
        )

        # Both should be created successfully
        assert concept1.structure_class_name == "test_domain__Person"
        assert concept2.structure_class_name == "test_domain__Product"

        # Both classes should be registered and independent
        person_class = get_class_registry().get_required_subclass("test_domain__Person", StructuredContent)
        product_class = get_class_registry().get_required_subclass("test_domain__Product", StructuredContent)

        assert person_class != product_class

        # Test instances are independent
        person = person_class(name="John Doe", age=30)
        product = product_class(name="Widget", age=365)

        assert person.name == "John Doe"
        assert product.name == "Widget"
        assert person.age == 30
        assert product.age == 365

    def test_inline_structure_with_quoted_descriptions(self):
        """Test that inline structures with quotes in descriptions work end-to-end."""
        # Real-world example: field descriptions containing quoted examples
        inline_structure: dict[str, str | ConceptStructureBlueprint] = {
            "animal_type": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description='The species or type of animal (e.g., "fox", "penguin", "octopus")',
                required=True,
            ),
            "owner_name": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description="The owner's full name with apostrophe",
                required=False,
            ),
            "habitat": ConceptStructureBlueprint(
                type=ConceptStructureBlueprintFieldType.TEXT,
                description='Natural habitat like "forest", "ocean", or "desert"',
                required=False,
            ),
        }

        # Create concept blueprint with inline structure
        blueprint = ConceptBlueprint(description="Information about an animal", structure=inline_structure)

        # Create concept from blueprint
        concept = ConceptFactory.make_from_blueprint(
            domain_code="test_domain",
            concept_code="AnimalInfo",
            blueprint_or_string_description=blueprint,
        )

        # Verify concept properties
        assert concept.domain_code == "test_domain"
        assert concept.code == "AnimalInfo"
        assert concept.structure_class_name == "test_domain__AnimalInfo"

        # Verify the generated class is registered and accessible
        assert get_class_registry().has_class("test_domain__AnimalInfo")
        generated_class = get_class_registry().get_required_subclass("test_domain__AnimalInfo", StructuredContent)

        # Test instantiation with quoted data
        instance = generated_class(
            animal_type="fox",  # pyright: ignore[reportCallIssue]
            owner_name="John's Pet Store",  # pyright: ignore[reportCallIssue]
            habitat="forest",  # pyright: ignore[reportCallIssue]
        )

        assert instance.animal_type == "fox"  # type: ignore[attr-defined] # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
        assert instance.owner_name == "John's Pet Store"  # type: ignore[attr-defined] # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
        assert instance.habitat == "forest"  # type: ignore[attr-defined] # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
