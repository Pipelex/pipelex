"""Tests for StructureGenerator with concept-to-concept references.

This module tests the generation of Pydantic classes that have fields
referencing other concepts (type = "concept" with concept_ref).
"""

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from tests.unit.pipelex.core.concepts.structure_generation.class_shape import assert_same_class


class TestStructureGeneratorConceptRefs:
    """Test StructureGenerator with concept type fields."""

    def test_single_concept_ref_field_uses_forward_reference(self):
        """Test generation of a class with a single concept reference field uses forward reference."""
        structure_blueprint = {
            "customer": ConceptStructureBlueprint(
                description="The customer for this invoice",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="myapp.Customer",
                required=True,
            ),
            "total": ConceptStructureBlueprint(
                description="Invoice total",
                type=ConceptStructureBlueprintFieldType.NUMBER,
                required=True,
            ),
        }

        generator = StructureGenerator()
        generated_class = generator.generate_from_structure_blueprint(class_name="Invoice", structure_blueprint=structure_blueprint)

        expected_code = '''\
class Invoice(StructuredContent):
    """Generated Invoice class"""

    customer: "myapp__Customer" = Field(..., description="The customer for this invoice")
    total: float = Field(..., description="Invoice total")
'''
        assert_same_class(generated_class, expected_source=expected_code)
        assert issubclass(generated_class, StructuredContent)

    def test_list_of_concepts_uses_forward_reference(self):
        """Test generation of a class with a list of concept references uses forward reference."""
        structure_blueprint = {
            "line_items": ConceptStructureBlueprint(
                description="List of line items",
                type=ConceptStructureBlueprintFieldType.LIST,
                item_type="concept",
                item_concept_ref="myapp.LineItem",
                required=True,
            ),
            "total": ConceptStructureBlueprint(
                description="Invoice total",
                type=ConceptStructureBlueprintFieldType.NUMBER,
                required=True,
            ),
        }

        generator = StructureGenerator()
        generated_class = generator.generate_from_structure_blueprint(class_name="Invoice", structure_blueprint=structure_blueprint)

        expected_code = '''\
class Invoice(StructuredContent):
    """Generated Invoice class"""

    line_items: list["myapp__LineItem"] = Field(..., description="List of line items")
    total: float = Field(..., description="Invoice total")
'''
        assert_same_class(generated_class, expected_source=expected_code)
        assert issubclass(generated_class, StructuredContent)

    def test_optional_concept_ref_field_uses_forward_reference(self):
        """Test generation of an optional concept reference field uses forward reference."""
        structure_blueprint = {
            "parent": ConceptStructureBlueprint(
                description="Optional parent reference",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="myapp.Category",
                required=False,
            ),
            "name": ConceptStructureBlueprint(
                description="Category name",
                type=ConceptStructureBlueprintFieldType.TEXT,
                required=True,
            ),
        }

        generator = StructureGenerator()
        generated_class = generator.generate_from_structure_blueprint(class_name="CategoryNode", structure_blueprint=structure_blueprint)

        expected_code = '''\
class CategoryNode(StructuredContent):
    """Generated CategoryNode class"""

    parent: Optional["myapp__Category"] = Field(default=None, description="Optional parent reference")
    name: str = Field(..., description="Category name")
'''
        assert_same_class(generated_class, expected_source=expected_code)
        assert issubclass(generated_class, StructuredContent)

    def test_optional_list_of_concepts_uses_forward_reference(self):
        """Test generation of an optional list of concept references uses forward reference."""
        structure_blueprint = {
            "children": ConceptStructureBlueprint(
                description="Optional child categories",
                type=ConceptStructureBlueprintFieldType.LIST,
                item_type="concept",
                item_concept_ref="myapp.Category",
                required=False,
            ),
        }

        generator = StructureGenerator()
        generated_class = generator.generate_from_structure_blueprint(class_name="Parent", structure_blueprint=structure_blueprint)

        expected_code = '''\
class Parent(StructuredContent):
    """Generated Parent class"""

    children: list["myapp__Category"] | None = Field(default=None, description="Optional child categories")
'''
        assert_same_class(generated_class, expected_source=expected_code)
        assert issubclass(generated_class, StructuredContent)

    def test_cross_domain_concept_ref_uses_forward_reference(self):
        """Test generation with cross-domain concept references uses forward references."""
        structure_blueprint = {
            "customer": ConceptStructureBlueprint(
                description="Customer from CRM domain",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="crm.Customer",
                required=True,
            ),
            "products": ConceptStructureBlueprint(
                description="Products from inventory domain",
                type=ConceptStructureBlueprintFieldType.LIST,
                item_type="concept",
                item_concept_ref="inventory.Product",
                required=True,
            ),
        }

        generator = StructureGenerator()
        generated_class = generator.generate_from_structure_blueprint(class_name="Order", structure_blueprint=structure_blueprint)

        expected_code = '''\
class Order(StructuredContent):
    """Generated Order class"""

    customer: "crm__Customer" = Field(..., description="Customer from CRM domain")
    products: list["inventory__Product"] = Field(..., description="Products from inventory domain")
'''
        assert_same_class(generated_class, expected_source=expected_code)
        assert issubclass(generated_class, StructuredContent)

    def test_concept_ref_without_mapping_uses_forward_reference(self):
        """Test that concept_ref without mapping uses forward reference."""
        structure_blueprint = {
            "item": ConceptStructureBlueprint(
                description="An item reference",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="unknown_domain.SomeItem",
                required=True,
            ),
        }

        generator = StructureGenerator()
        generated_class = generator.generate_from_structure_blueprint(class_name="Container", structure_blueprint=structure_blueprint)

        expected_code = '''\
class Container(StructuredContent):
    """Generated Container class"""

    item: "unknown_domain__SomeItem" = Field(..., description="An item reference")
'''
        assert_same_class(generated_class, expected_source=expected_code)
        assert issubclass(generated_class, StructuredContent)

    def test_mixed_concept_and_primitive_fields_uses_forward_references(self):
        """Test generation with a mix of concept references and primitive fields uses forward references."""
        structure_blueprint = {
            "id": ConceptStructureBlueprint(
                description="Unique identifier",
                type=ConceptStructureBlueprintFieldType.INTEGER,
                required=True,
            ),
            "name": ConceptStructureBlueprint(
                description="Name",
                type=ConceptStructureBlueprintFieldType.TEXT,
                required=True,
            ),
            "owner": ConceptStructureBlueprint(
                description="Owner reference",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="myapp.User",
                required=False,
            ),
            "tags": ConceptStructureBlueprint(
                description="Tags",
                type=ConceptStructureBlueprintFieldType.LIST,
                item_type="text",
                required=False,
            ),
            "related_items": ConceptStructureBlueprint(
                description="Related items",
                type=ConceptStructureBlueprintFieldType.LIST,
                item_type="concept",
                item_concept_ref="myapp.Item",
                required=False,
            ),
            "metadata": ConceptStructureBlueprint(
                description="Metadata",
                type=ConceptStructureBlueprintFieldType.DICT,
                key_type="text",
                value_type="text",
                required=False,
            ),
        }

        generator = StructureGenerator()
        generated_class = generator.generate_from_structure_blueprint(class_name="ComplexEntity", structure_blueprint=structure_blueprint)

        expected_code = '''\
class ComplexEntity(StructuredContent):
    """Generated ComplexEntity class"""

    id: int = Field(..., description="Unique identifier")
    name: str = Field(..., description="Name")
    owner: Optional["myapp__User"] = Field(default=None, description="Owner reference")
    tags: list[str] | None = Field(default=None, description="Tags")
    related_items: list["myapp__Item"] | None = Field(default=None, description="Related items")
    metadata: dict[str, str] | None = Field(default=None, description="Metadata")
'''
        assert_same_class(generated_class, expected_source=expected_code)
        assert issubclass(generated_class, StructuredContent)

    def test_native_concept_ref_uses_its_content_class(self):
        """Test generation with native concept references (e.g., native.Html) is annotated with its content class."""
        structure_blueprint = {
            "html_report": ConceptStructureBlueprint(
                description="HTML report content",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="native.Html",
                required=True,
            ),
        }

        generator = StructureGenerator()
        generated_class = generator.generate_from_structure_blueprint(class_name="ReportWrapper", structure_blueprint=structure_blueprint)

        # A native concept is annotated with its content class
        assert generated_class.model_fields["html_report"].annotation is HtmlContent  # pyright: ignore[reportAttributeAccessIssue]
        assert generated_class.model_fields["html_report"].is_required()  # pyright: ignore[reportAttributeAccessIssue]
        assert issubclass(generated_class, StructuredContent)

    def test_native_text_concept_ref_uses_text_content(self):
        """Test generation with native.Text concept reference is annotated with its content class."""
        structure_blueprint = {
            "text_content": ConceptStructureBlueprint(
                description="Text content reference",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="native.Text",
                required=True,
            ),
        }

        generator = StructureGenerator()
        generated_class = generator.generate_from_structure_blueprint(class_name="TextWrapper", structure_blueprint=structure_blueprint)

        # A native concept is annotated with its content class
        assert generated_class.model_fields["text_content"].annotation is TextContent  # pyright: ignore[reportAttributeAccessIssue]
        assert generated_class.model_fields["text_content"].is_required()  # pyright: ignore[reportAttributeAccessIssue]
        assert issubclass(generated_class, StructuredContent)

    def test_list_of_native_concepts_uses_their_content_class(self):
        """Test generation with list of native concept references is annotated with its content class."""
        structure_blueprint = {
            "images": ConceptStructureBlueprint(
                description="List of images",
                type=ConceptStructureBlueprintFieldType.LIST,
                item_type="concept",
                item_concept_ref="native.Image",
                required=True,
            ),
        }

        generator = StructureGenerator()
        generated_class = generator.generate_from_structure_blueprint(class_name="ImageGallery", structure_blueprint=structure_blueprint)

        # A list of native concepts is a list of their content class
        assert generated_class.model_fields["images"].annotation == list[ImageContent]  # pyright: ignore[reportAttributeAccessIssue]
        assert generated_class.model_fields["images"].is_required()  # pyright: ignore[reportAttributeAccessIssue]
        assert issubclass(generated_class, StructuredContent)
