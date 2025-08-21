"""Tests for structured output generator."""

from typing import Dict

from pipelex import pretty_print
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.create.structured_output_generator import (
    StructureGenerator,
    generate_structured_output_from_blueprint_dict,
)


class TestStructureGenerator:
    def test_simple_structure_generation(self):
        """Test generation of a simple structure with basic fields."""
        structure_blueprint = {
            "name": ConceptStructureBlueprint(definition="Name field", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "age": ConceptStructureBlueprint(definition="Age field", type=ConceptStructureBlueprintFieldType.INTEGER, required=False),
            "active": ConceptStructureBlueprint(
                definition="Active status", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False, default_value=True
            ),
        }

        generator = StructureGenerator()
        result = generator.generate_from_structure_blueprint("TestModel", structure_blueprint)

        pretty_print(structure_blueprint, title="Source Blueprint")
        pretty_print(result, title="Generated Result")

        # Check that basic structure is correct
        assert "from typing import Optional" in result
        assert "from pipelex.core.stuffs.stuff_content import StructuredContent" in result
        assert "from pydantic import Field" in result
        assert "class TestModel(StructuredContent):" in result
        assert '"""Generated TestModel class"""' in result
        assert 'name: str = Field(..., description="Name field")' in result
        assert 'age: Optional[int] = Field(default=None, description="Age field")' in result
        assert 'active: Optional[bool] = Field(default=True, description="Active status")' in result

    def test_complex_types_generation(self):
        """Test generation with complex types like lists and dicts."""
        structure_blueprint = {
            "tags": ConceptStructureBlueprint(
                definition="List of tags", type=ConceptStructureBlueprintFieldType.LIST, item_type="text", required=False
            ),
            "metadata": ConceptStructureBlueprint(
                definition="Metadata dictionary", type=ConceptStructureBlueprintFieldType.DICT, key_type="text", value_type="text", required=False
            ),
            "scores": ConceptStructureBlueprint(
                definition="List of scores", type=ConceptStructureBlueprintFieldType.LIST, item_type="number", required=True
            ),
        }

        generator = StructureGenerator()
        result = generator.generate_from_structure_blueprint("ComplexModel", structure_blueprint)

        pretty_print(structure_blueprint, title="Source Blueprint")
        pretty_print(result, title="Generated Result")

        assert 'tags: Optional[List[str]] = Field(default=None, description="List of tags")' in result
        assert 'metadata: Optional[Dict[str, str]] = Field(default=None, description="Metadata dictionary")' in result
        assert 'scores: List[float] = Field(..., description="List of scores")' in result

    def test_choices_generation(self):
        """Test generation with inline choices (Literal type)."""
        structure_blueprint = {
            "name": ConceptStructureBlueprint(definition="Product name", type=ConceptStructureBlueprintFieldType.TEXT, required=False),
            "category": ConceptStructureBlueprint(definition="Product category", choices=["electronics", "clothing", "food", "books"], required=True),
            "size": ConceptStructureBlueprint(definition="Size of the product", choices=["XS", "S", "M", "L", "XL"], required=False),
        }

        generator = StructureGenerator()
        result = generator.generate_from_structure_blueprint("Product", structure_blueprint)

        pretty_print(structure_blueprint, title="Source Blueprint")
        pretty_print(result, title="Generated Result")

        # Check Literal type usage
        assert "from typing import Optional, List, Dict, Any, Literal" in result
        assert "category: Literal['electronics', 'clothing', 'food', 'books'] = Field(..., description=\"Product category\")" in result
        assert "size: Optional[Literal['XS', 'S', 'M', 'L', 'XL']] = Field(default=None, description=\"Size of the product\")" in result

    def test_empty_structure(self):
        """Test generation of structure with no fields."""
        structure_blueprint: Dict[str, ConceptStructureBlueprint] = {}

        generator = StructureGenerator()
        result = generator.generate_from_structure_blueprint("EmptyModel", structure_blueprint)

        pretty_print(structure_blueprint, title="Source Blueprint")
        pretty_print(result, title="Generated Result")

        assert "class EmptyModel(StructuredContent):" in result
        assert '"""Generated EmptyModel class"""' in result
        assert "pass" in result

    def test_concept_get_structure_method(self):
        """Test the get_structure method on Concept class."""
        structure_blueprint = {
            "title": ConceptStructureBlueprint(definition="Document title", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "page_count": ConceptStructureBlueprint(definition="Number of pages", type=ConceptStructureBlueprintFieldType.INTEGER, required=False),
        }

        result = Concept.get_structure("DocumentInfo", structure_blueprint)

        pretty_print(structure_blueprint, title="Source Blueprint")
        pretty_print(result, title="Generated Result")

        assert "class DocumentInfo(StructuredContent):" in result
        assert 'title: str = Field(..., description="Document title")' in result
        assert 'page_count: Optional[int] = Field(default=None, description="Number of pages")' in result

    def test_generate_from_blueprint_dict_function(self):
        """Test the convenience function for generating from blueprint dict."""
        structure_blueprint = {
            "value": ConceptStructureBlueprint(definition="Test value", type=ConceptStructureBlueprintFieldType.TEXT, required=True)
        }

        result = generate_structured_output_from_blueprint_dict("ConvenienceTest", structure_blueprint)

        pretty_print(structure_blueprint, title="Source Blueprint")
        pretty_print(result, title="Generated Result")

        assert "class ConvenienceTest(StructuredContent):" in result
        assert 'value: str = Field(..., description="Test value")' in result

    def test_all_field_types(self):
        """Test that all field types are properly handled."""
        structure_blueprint = {
            "text_field": ConceptStructureBlueprint(definition="Text field", type=ConceptStructureBlueprintFieldType.TEXT, required=False),
            "number_field": ConceptStructureBlueprint(definition="Number field", type=ConceptStructureBlueprintFieldType.NUMBER, required=False),
            "integer_field": ConceptStructureBlueprint(definition="Integer field", type=ConceptStructureBlueprintFieldType.INTEGER, required=False),
            "boolean_field": ConceptStructureBlueprint(definition="Boolean field", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False),
            "list_field": ConceptStructureBlueprint(
                definition="List field", type=ConceptStructureBlueprintFieldType.LIST, item_type="text", required=False
            ),
            "dict_field": ConceptStructureBlueprint(
                definition="Dict field", type=ConceptStructureBlueprintFieldType.DICT, key_type="text", value_type="integer", required=False
            ),
        }

        generator = StructureGenerator()
        result = generator.generate_from_structure_blueprint("TypeMappingTest", structure_blueprint)

        pretty_print(structure_blueprint, title="Source Blueprint")
        pretty_print(result, title="Generated Result")

        assert "text_field: Optional[str]" in result
        assert "number_field: Optional[float]" in result
        assert "integer_field: Optional[int]" in result
        assert "boolean_field: Optional[bool]" in result
        assert "list_field: Optional[List[str]]" in result
        assert "dict_field: Optional[Dict[str, int]]" in result

    def test_required_vs_optional_fields(self):
        """Test that fields can be marked as required vs optional."""
        structure_blueprint = {
            "title": ConceptStructureBlueprint(definition="Required title", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "optional_field": ConceptStructureBlueprint(definition="Optional field", type=ConceptStructureBlueprintFieldType.TEXT, required=False),
        }

        generator = StructureGenerator()
        result = generator.generate_from_structure_blueprint("RequiredFieldsModel", structure_blueprint)

        pretty_print(structure_blueprint, title="Source Blueprint")
        pretty_print(result, title="Generated Result")

        assert 'title: str = Field(..., description="Required title")' in result
        assert 'optional_field: Optional[str] = Field(default=None, description="Optional field")' in result

    def test_default_values(self):
        """Test fields with default values."""
        structure_blueprint = {
            "name": ConceptStructureBlueprint(
                definition="Person name", type=ConceptStructureBlueprintFieldType.TEXT, required=False, default_value="Anonymous"
            ),
            "age": ConceptStructureBlueprint(
                definition="Person age", type=ConceptStructureBlueprintFieldType.INTEGER, required=False, default_value=0
            ),
            "active": ConceptStructureBlueprint(
                definition="Is active", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False, default_value=True
            ),
        }

        generator = StructureGenerator()
        result = generator.generate_from_structure_blueprint("PersonWithDefaults", structure_blueprint)

        pretty_print(structure_blueprint, title="Source Blueprint")
        pretty_print(result, title="Generated Result")

        assert 'name: Optional[str] = Field(default="Anonymous", description="Person name")' in result
        assert 'age: Optional[int] = Field(default=0, description="Person age")' in result
        assert 'active: Optional[bool] = Field(default=True, description="Is active")' in result

    def test_nested_list_types(self):
        """Test nested list types with different item types."""
        structure_blueprint = {
            "text_list": ConceptStructureBlueprint(
                definition="List of text items", type=ConceptStructureBlueprintFieldType.LIST, item_type="text", required=False
            ),
            "number_list": ConceptStructureBlueprint(
                definition="List of numbers", type=ConceptStructureBlueprintFieldType.LIST, item_type="number", required=True
            ),
            "integer_list": ConceptStructureBlueprint(
                definition="List of integers", type=ConceptStructureBlueprintFieldType.LIST, item_type="integer", required=False
            ),
        }

        generator = StructureGenerator()
        result = generator.generate_from_structure_blueprint("ListTypesModel", structure_blueprint)

        pretty_print(structure_blueprint, title="Source Blueprint")
        pretty_print(result, title="Generated Result")

        assert 'text_list: Optional[List[str]] = Field(default=None, description="List of text items")' in result
        assert 'number_list: List[float] = Field(..., description="List of numbers")' in result
        assert 'integer_list: Optional[List[int]] = Field(default=None, description="List of integers")' in result

    def test_nested_dict_types(self):
        """Test nested dict types with different key/value combinations."""
        structure_blueprint = {
            "string_to_string": ConceptStructureBlueprint(
                definition="String to string mapping",
                type=ConceptStructureBlueprintFieldType.DICT,
                key_type="text",
                value_type="text",
                required=False,
            ),
            "string_to_number": ConceptStructureBlueprint(
                definition="String to number mapping",
                type=ConceptStructureBlueprintFieldType.DICT,
                key_type="text",
                value_type="number",
                required=True,
            ),
            "string_to_integer": ConceptStructureBlueprint(
                definition="String to integer mapping",
                type=ConceptStructureBlueprintFieldType.DICT,
                key_type="text",
                value_type="integer",
                required=False,
            ),
        }

        generator = StructureGenerator()
        result = generator.generate_from_structure_blueprint("DictTypesModel", structure_blueprint)

        pretty_print(structure_blueprint, title="Source Blueprint")
        pretty_print(result, title="Generated Result")

        assert 'string_to_string: Optional[Dict[str, str]] = Field(default=None, description="String to string mapping")' in result
        assert 'string_to_number: Dict[str, float] = Field(..., description="String to number mapping")' in result
        assert 'string_to_integer: Optional[Dict[str, int]] = Field(default=None, description="String to integer mapping")' in result

    def test_mixed_complexity_structure(self):
        """Test a structure with mixed complexity - simple and complex types together."""
        structure_blueprint = {
            "id": ConceptStructureBlueprint(definition="Unique identifier", type=ConceptStructureBlueprintFieldType.INTEGER, required=True),
            "name": ConceptStructureBlueprint(definition="Display name", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
            "tags": ConceptStructureBlueprint(
                definition="Associated tags", type=ConceptStructureBlueprintFieldType.LIST, item_type="text", required=False
            ),
            "metadata": ConceptStructureBlueprint(
                definition="Additional metadata", type=ConceptStructureBlueprintFieldType.DICT, key_type="text", value_type="text", required=False
            ),
            "active": ConceptStructureBlueprint(
                definition="Whether item is active", type=ConceptStructureBlueprintFieldType.BOOLEAN, required=False, default_value=True
            ),
            "priority": ConceptStructureBlueprint(
                definition="Priority level", choices=["low", "medium", "high", "urgent"], required=False, default_value="medium"
            ),
        }

        generator = StructureGenerator()
        result = generator.generate_from_structure_blueprint("ComplexItem", structure_blueprint)

        pretty_print(structure_blueprint, title="Source Blueprint")
        pretty_print(result, title="Generated Result")

        # Check all field types are correctly generated
        assert 'id: int = Field(..., description="Unique identifier")' in result
        assert 'name: str = Field(..., description="Display name")' in result
        assert 'tags: Optional[List[str]] = Field(default=None, description="Associated tags")' in result
        assert 'metadata: Optional[Dict[str, str]] = Field(default=None, description="Additional metadata")' in result
        assert 'active: Optional[bool] = Field(default=True, description="Whether item is active")' in result
        assert "priority: Optional[Literal['low', 'medium', 'high', 'urgent']] = Field(default='medium', description=\"Priority level\")" in result
