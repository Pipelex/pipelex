"""Tests for structured output generator."""

import pytest

from pipelex import pretty_print
from pipelex.create.structured_output_generator import (
    StructuredOutputGenerator,
    generate_structured_output_from_inline_definition,
    generate_structured_outputs_from_toml_string,
)


class TestStructuredOutputGenerator:
    def test_simple_structure_generation(self):
        """Test generation of a simple structure with basic fields."""
        toml_content = """
[structure.TestModel]
definition = "A test model"

[structure.TestModel.fields]
name = { type = "text", definition = "Name field", required = true }
age = { type = "integer", definition = "Age field" }
active = { type = "boolean", definition = "Active status", default = true }
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        # Check that basic structure is correct
        assert "from typing import Optional" in result
        assert "from pipelex.core.stuffs.stuff_content import StructuredContent" in result
        assert "from pydantic import Field" in result
        assert "class TestModel(StructuredContent):" in result
        assert '"""A test model"""' in result
        assert 'name: str = Field(..., description="Name field")' in result
        assert 'age: Optional[int] = Field(default=None, description="Age field")' in result
        assert 'active: Optional[bool] = Field(default=True, description="Active status")' in result

    def test_simplified_field_syntax(self):
        """Test the simplified field syntax where a field is just a string definition."""
        toml_content = """
[structure.SimpleModel]
definition = "A model with simplified field syntax"

[structure.SimpleModel.fields]
dominant_feature = "The most important or dominant feature in the image"
simple_text = "Just some text"
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        assert 'dominant_feature: Optional[str] = Field(default=None, description="The most important or dominant feature in the image")' in result
        assert 'simple_text: Optional[str] = Field(default=None, description="Just some text")' in result

    def test_complex_types_generation(self):
        """Test generation with complex types like lists and dicts."""
        toml_content = """
[structure.ComplexModel]
definition = "A model with complex types"

[structure.ComplexModel.fields]
tags = { type = "list", item_type = "text", definition = "List of tags" }
metadata = { type = "dict", key_type = "text", value_type = "text", definition = "Metadata dictionary" }
scores = { type = "list", item_type = "number", definition = "List of scores", required = true }
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        assert 'tags: Optional[List[str]] = Field(default=None, description="List of tags")' in result
        assert 'metadata: Optional[Dict[str, str]] = Field(default=None, description="Metadata dictionary")' in result
        assert 'scores: List[float] = Field(..., description="List of scores")' in result

    def test_multiple_structures(self):
        """Test generation of multiple structures in one TOML."""
        toml_content = """
[structure.FirstModel]
definition = "First model"

[structure.FirstModel.fields]
title = { type = "text", definition = "Title", required = true }

[structure.SecondModel]  
definition = "Second model"

[structure.SecondModel.fields]
content = { type = "text", definition = "Content" }
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        assert "class FirstModel(StructuredContent):" in result
        assert "class SecondModel(StructuredContent):" in result
        assert '"""First model"""' in result
        assert '"""Second model"""' in result

    def test_empty_structure(self):
        """Test generation of structure with no fields."""
        toml_content = """
[structure.EmptyModel]
definition = "An empty model"
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        assert "class EmptyModel(StructuredContent):" in result
        assert '"""An empty model"""' in result
        assert "pass" in result

    def test_required_field_syntax(self):
        """Test that fields can be marked as required."""
        toml_content = """
[structure.RequiredFieldsModel]
definition = "Model with required fields"

[structure.RequiredFieldsModel.fields]
title = { type = "text", definition = "Required title", required = true }
optional_field = { type = "text", definition = "Optional field" }
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        assert 'title: str = Field(..., description="Required title")' in result
        assert 'optional_field: Optional[str] = Field(default=None, description="Optional field")' in result

    def test_custom_types(self):
        """Test handling of custom/unknown types."""
        toml_content = """
[structure.CustomTypeModel]
definition = "Model with custom types"

[structure.CustomTypeModel.fields]
custom_field = { type = "CustomClass", definition = "Custom class field" }
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        assert 'custom_field: Optional[CustomClass] = Field(default=None, description="Custom class field")' in result

    def test_missing_structure_section_raises_error(self):
        """Test that missing structure section raises appropriate error."""
        toml_content = """
[other_section]
value = "test"
"""

        generator = StructuredOutputGenerator()

        pretty_print(toml_content, title="Source TOML (should raise error)")

        with pytest.raises(ValueError, match="TOML must contain a 'structure' section"):
            generator.generate_from_toml(toml_content)

    def test_generate_from_string_convenience_function(self):
        """Test the convenience function for generating from string."""
        toml_content = """
[structure.ConvenienceTest]
definition = "Test convenience function"

[structure.ConvenienceTest.fields]
value = { type = "text", definition = "Test value", required = true }
"""

        result = generate_structured_outputs_from_toml_string(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        assert "class ConvenienceTest(StructuredContent):" in result
        assert 'value: str = Field(..., description="Test value")' in result

    def test_field_type_enum_usage(self):
        """Test that FieldType enum values are properly handled."""
        toml_content = """
[structure.TypeMappingTest]
definition = "Test all type mappings"

[structure.TypeMappingTest.fields]
text_field = { type = "text", definition = "Text field" }
number_field = { type = "number", definition = "Number field" }
integer_field = { type = "integer", definition = "Integer field" }
boolean_field = { type = "boolean", definition = "Boolean field" }
list_field = { type = "list", item_type = "text", definition = "List field" }
dict_field = { type = "dict", key_type = "text", value_type = "integer", definition = "Dict field" }
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        assert "text_field: Optional[str]" in result
        assert "number_field: Optional[float]" in result
        assert "integer_field: Optional[int]" in result
        assert "boolean_field: Optional[bool]" in result
        assert "list_field: Optional[List[str]]" in result
        assert "dict_field: Optional[Dict[str, int]]" in result

    def test_mixed_field_syntax(self):
        """Test mixing simplified syntax with full field definitions."""
        toml_content = """
[structure.MixedSyntaxModel]
definition = "Model with mixed field syntax"

[structure.MixedSyntaxModel.fields]
# Simplified syntax
simple_description = "A simple text description"
# Full syntax
complex_field = { type = "integer", definition = "A complex field", required = true }
another_simple = "Another simple field"
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        assert 'simple_description: Optional[str] = Field(default=None, description="A simple text description")' in result
        assert 'complex_field: int = Field(..., description="A complex field")' in result
        assert 'another_simple: Optional[str] = Field(default=None, description="Another simple field")' in result

    def test_enum_generation_simple_list(self):
        """Test generation of enum with simple list of values."""
        toml_content = """
[enum.OrderStatus]
definition = "Possible states of an order"
values = ["pending", "processing", "shipped", "delivered", "cancelled"]

[structure.Order]
definition = "An order in the system"

[structure.Order.fields]
order_id = "Unique identifier for the order"
status = { type = "OrderStatus", definition = "Current status of the order", required = true }
customer_name = "Name of the customer"
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        # Check enum generation
        assert "from enum import Enum" in result
        assert "class OrderStatus(str, Enum):" in result
        assert '"""Possible states of an order"""' in result
        assert 'PENDING = "pending"' in result
        assert 'PROCESSING = "processing"' in result
        assert 'SHIPPED = "shipped"' in result
        assert 'DELIVERED = "delivered"' in result
        assert 'CANCELLED = "cancelled"' in result

        # Check schema using the enum
        assert "class Order(StructuredContent):" in result
        assert 'status: OrderStatus = Field(..., description="Current status of the order")' in result

    def test_enum_generation_with_descriptions(self):
        """Test generation of enum with key-value pairs (descriptions)."""
        toml_content = """
[enum.Priority]
definition = "Task priority levels"

[enum.Priority.values]
low = "Low Priority"
medium = "Medium Priority"
high = "High Priority"
urgent = "Urgent - Handle Immediately"

[structure.Task]
definition = "A task to be completed"

[structure.Task.fields]
title = "Task title"
priority = { type = "Priority", definition = "How urgent is this task", required = true }
assigned_to = "Person responsible for the task"
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        # Check enum generation with descriptions
        assert "class Priority(str, Enum):" in result
        assert '"""Task priority levels"""' in result
        assert 'LOW = "low"  # Low Priority' in result
        assert 'MEDIUM = "medium"  # Medium Priority' in result
        assert 'HIGH = "high"  # High Priority' in result
        assert 'URGENT = "urgent"  # Urgent - Handle Immediately' in result

        # Check schema using the enum
        assert 'priority: Priority = Field(..., description="How urgent is this task")' in result

    def test_inline_choices(self):
        """Test generation with inline choices (Literal type)."""
        toml_content = """
[structure.Product]
definition = "A product in our catalog"

[structure.Product.fields]
name = "Product name"
category = { choices = ["electronics", "clothing", "food", "books"], definition = "Product category", required = true }
size = { choices = ["XS", "S", "M", "L", "XL"], definition = "Size of the product" }
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        # Check Literal type usage
        assert "from typing import Optional, List, Dict, Any, Literal" in result
        assert "category: Literal['electronics', 'clothing', 'food', 'books'] = Field(..., description=\"Product category\")" in result
        assert "size: Optional[Literal['XS', 'S', 'M', 'L', 'XL']] = Field(default=None, description=\"Size of the product\")" in result

    def test_mixed_enums_and_inline_choices(self):
        """Test combining enum references and inline choices in the same schema."""
        toml_content = """
[enum.Color]
definition = "Available colors"
values = ["red", "blue", "green", "yellow", "black", "white"]

[enum.ShippingMethod]
definition = "How the product will be shipped"
values = ["standard", "express", "overnight", "pickup"]

[structure.ProductVariant]
definition = "A specific variant of a product"

[structure.ProductVariant.fields]
sku = "Stock keeping unit"
color = { type = "Color", definition = "Color of this variant" }
size = { choices = ["S", "M", "L"], definition = "Size options" }
shipping_method = { type = "ShippingMethod", definition = "Shipping option", required = true }
availability = { choices = ["in_stock", "out_of_stock", "pre_order"], definition = "Current availability" }
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        # Check enums are generated
        assert "class Color(str, Enum):" in result
        assert "class ShippingMethod(str, Enum):" in result

        # Check mixed usage in schema
        assert 'color: Optional[Color] = Field(default=None, description="Color of this variant")' in result
        assert "size: Optional[Literal['S', 'M', 'L']] = Field(default=None, description=\"Size options\")" in result
        assert 'shipping_method: ShippingMethod = Field(..., description="Shipping option")' in result
        assert (
            "availability: Optional[Literal['in_stock', 'out_of_stock', 'pre_order']] = Field(default=None, description=\"Current availability\")"
            in result
        )

    def test_enum_in_list_field(self):
        """Test using enum types in list fields."""
        toml_content = """
[enum.DietaryRestriction]
definition = "Dietary restrictions and preferences"
values = ["vegetarian", "vegan", "gluten_free", "dairy_free", "nut_free"]

[structure.MenuItem]
definition = "An item on the restaurant menu"

[structure.MenuItem.fields]
name = "Name of the dish"
dietary_info = { type = "list", item_type = "DietaryRestriction", definition = "Dietary accommodations" }
tags = { type = "list", item_type = "text", definition = "General tags" }
"""

        generator = StructuredOutputGenerator()
        result = generator.generate_from_toml(toml_content)

        pretty_print(toml_content, title="Source TOML")
        pretty_print(result, title="Generated Result")

        # Check enum is generated
        assert "class DietaryRestriction(str, Enum):" in result
        assert 'VEGETARIAN = "vegetarian"' in result
        assert 'GLUTEN_FREE = "gluten_free"' in result

        # Check list with enum type
        assert 'dietary_info: Optional[List[DietaryRestriction]] = Field(default=None, description="Dietary accommodations")' in result
        assert 'tags: Optional[List[str]] = Field(default=None, description="General tags")' in result

    def test_inline_structure_definition(self):
        """Test generating structure from inline field definitions (for concept integration)."""
        fields_def = {
            "document_type": {"type": "DocumentType", "definition": "Classified document type", "required": True},
            "priority": {"type": "Priority", "definition": "Processing priority", "required": True},
            "title": "Inferred document title",
            "summary": "Brief document summary",
            "page_count": {"type": "integer", "definition": "Total number of pages"},
            "language": {"choices": ["en", "fr", "es", "de"], "definition": "Document language"},
        }

        enums = {
            "DocumentType": {
                "definition": "Types of documents we can process",
                "values": ["technical", "legal", "financial", "marketing", "general"],
            },
            "Priority": {"definition": "Document processing priority", "values": ["low", "medium", "high", "urgent"]},
        }

        result = generate_structured_output_from_inline_definition("DocumentMetadata", fields_def, enums)

        pretty_print(fields_def, title="Inline Field Definition")
        pretty_print(result, title="Generated Result")

        # Check enum generation
        assert "class DocumentType(str, Enum):" in result
        assert "class Priority(str, Enum):" in result
        assert 'TECHNICAL = "technical"' in result
        assert 'LOW = "low"' in result

        # Check structure generation
        assert "class DocumentMetadata(StructuredContent):" in result
        assert 'document_type: DocumentType = Field(..., description="Classified document type")' in result
        assert 'priority: Priority = Field(..., description="Processing priority")' in result
        assert 'title: Optional[str] = Field(default=None, description="Inferred document title")' in result
        assert 'page_count: Optional[int] = Field(default=None, description="Total number of pages")' in result
        assert "language: Optional[Literal['en', 'fr', 'es', 'de']] = Field(default=None, description=\"Document language\")" in result
