"""Tests for StructureGenerator with concept-to-concept references.

This module tests the generation of Pydantic classes that have fields
referencing other concepts (type = "concept" with concept_ref).
"""

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.structure_generation.generator import ConceptClassInfo, StructureGenerator
from pipelex.core.stuffs.structured_content import StructuredContent


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

        # No concept_ref_to_class_info - uses forward references
        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("Invoice", structure_blueprint)

        # Should use forward reference (with quotes)
        assert 'customer: "Customer" = Field(..., description=' in generated_code
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
        generated_code, generated_class = generator.generate_from_structure_blueprint("Invoice", structure_blueprint)

        assert 'line_items: List["LineItem"] = Field(..., description=' in generated_code
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
        generated_code, generated_class = generator.generate_from_structure_blueprint("CategoryNode", structure_blueprint)

        assert 'parent: Optional["Category"] = Field(default=None, description=' in generated_code
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
        generated_code, generated_class = generator.generate_from_structure_blueprint("Parent", structure_blueprint)

        assert 'children: Optional[List["Category"]] = Field(default=None, description=' in generated_code
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
        generated_code, generated_class = generator.generate_from_structure_blueprint("Order", structure_blueprint)

        assert 'customer: "Customer" = Field(..., description=' in generated_code
        assert 'products: List["Product"] = Field(..., description=' in generated_code
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
        generated_code, generated_class = generator.generate_from_structure_blueprint("Container", structure_blueprint)

        # Should use forward reference
        assert 'item: "SomeItem" = Field(..., description=' in generated_code
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
        generated_code, generated_class = generator.generate_from_structure_blueprint("ComplexEntity", structure_blueprint)

        assert "id: int = Field(..., description=" in generated_code
        assert "name: str = Field(..., description=" in generated_code
        assert 'owner: Optional["User"] = Field(default=None, description=' in generated_code
        assert "tags: Optional[List[str]] = Field(default=None, description=" in generated_code
        assert 'related_items: Optional[List["Item"]] = Field(default=None, description=' in generated_code
        assert "metadata: Optional[Dict[str, str]] = Field(default=None, description=" in generated_code
        assert issubclass(generated_class, StructuredContent)

    def test_native_concept_ref_uses_forward_reference(self):
        """Test generation with native concept references uses forward reference."""
        structure_blueprint = {
            "text_content": ConceptStructureBlueprint(
                description="Text content reference",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="native.TextContent",
                required=True,
            ),
        }

        generator = StructureGenerator()
        generated_code, generated_class = generator.generate_from_structure_blueprint("Wrapper", structure_blueprint)

        assert 'text_content: "TextContent" = Field(..., description=' in generated_code
        assert issubclass(generated_class, StructuredContent)

    def test_concept_ref_with_module_path_generates_import(self):
        """Test that concept_ref with module_path generates proper import statements."""
        structure_blueprint = {
            "skill": ConceptStructureBlueprint(
                description="The skill being evaluated",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="cv_tech_screening.Skill",
                required=True,
            ),
            "matches_requirement": ConceptStructureBlueprint(
                description="Whether this skill matches a job requirement",
                type=ConceptStructureBlueprintFieldType.BOOLEAN,
                required=True,
            ),
        }

        concept_ref_to_class_info = {
            "cv_tech_screening.Skill": ConceptClassInfo(
                class_name="Skill",
                module_path="pipeline_01.structures.cv_tech_screening__skill",
            ),
        }

        generator = StructureGenerator(concept_ref_to_class_info=concept_ref_to_class_info)

        # Generate the class code without full validation (imports would fail)
        class_code = generator._generate_class_source_code_from_blueprint("SkillMatchResult", structure_blueprint)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        imports_section = "\n".join(sorted(generator.imports))

        # Check the import was generated correctly
        assert "from pipeline_01.structures.cv_tech_screening__skill import Skill" in imports_section

        # Check the field uses the class name directly (not as a forward reference string)
        assert "skill: Skill = Field(..., description=" in class_code
        assert '"Skill"' not in class_code  # Should NOT be a forward reference

    def test_list_of_concepts_with_module_path_generates_import(self):
        """Test that list of concepts with module_path generates proper import statements."""
        structure_blueprint = {
            "skill_matches": ConceptStructureBlueprint(
                description="List of skill match results",
                type=ConceptStructureBlueprintFieldType.LIST,
                item_type="concept",
                item_concept_ref="cv_tech_screening.SkillMatchResult",
                required=True,
            ),
            "overall_score": ConceptStructureBlueprint(
                description="Overall match score",
                type=ConceptStructureBlueprintFieldType.INTEGER,
                required=True,
            ),
        }

        concept_ref_to_class_info = {
            "cv_tech_screening.SkillMatchResult": ConceptClassInfo(
                class_name="SkillMatchResult",
                module_path="pipeline_01.structures.cv_tech_screening__skill_match_result",
            ),
        }

        generator = StructureGenerator(concept_ref_to_class_info=concept_ref_to_class_info)

        # Generate the class code without full validation (imports would fail)
        class_code = generator._generate_class_source_code_from_blueprint("TechAnalysis", structure_blueprint)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        imports_section = "\n".join(sorted(generator.imports))

        # Check the import was generated correctly
        assert "from pipeline_01.structures.cv_tech_screening__skill_match_result import SkillMatchResult" in imports_section

        # Check the field uses the class name directly in List type (not as a forward reference string)
        assert "skill_matches: List[SkillMatchResult] = Field(..., description=" in class_code
        assert 'List["SkillMatchResult"]' not in class_code  # Should NOT be a forward reference

    def test_class_info_without_module_path_uses_forward_reference(self):
        """Test that ConceptClassInfo without module_path uses forward reference."""
        structure_blueprint = {
            "item": ConceptStructureBlueprint(
                description="An item reference",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="myapp.SomeItem",
                required=True,
            ),
        }

        concept_ref_to_class_info = {
            "myapp.SomeItem": ConceptClassInfo(
                class_name="SomeItem",
                module_path=None,  # No module path
            ),
        }

        generator = StructureGenerator(concept_ref_to_class_info=concept_ref_to_class_info)
        generated_code, generated_class = generator.generate_from_structure_blueprint("Container", structure_blueprint)

        # Should use forward reference since no module_path
        assert 'item: "SomeItem" = Field(..., description=' in generated_code
        assert issubclass(generated_class, StructuredContent)

    def test_multiple_concept_refs_with_same_class_name(self):
        """Test generation with multiple concept refs that have the same structure class name."""
        structure_blueprint = {
            "billing_customer": ConceptStructureBlueprint(
                description="The billing customer",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="billing.Customer",
                required=True,
            ),
            "shipping_customer": ConceptStructureBlueprint(
                description="The shipping customer",
                type=ConceptStructureBlueprintFieldType.CONCEPT,
                concept_ref="shipping.Customer",
                required=False,
            ),
        }

        concept_ref_to_class_info = {
            "billing.Customer": ConceptClassInfo(
                class_name="BillingCustomer",
                module_path="billing.structures.customer",
            ),
            "shipping.Customer": ConceptClassInfo(
                class_name="ShippingCustomer",
                module_path="shipping.structures.customer",
            ),
        }

        generator = StructureGenerator(concept_ref_to_class_info=concept_ref_to_class_info)

        # Generate the class code without full validation (imports would fail)
        class_code = generator._generate_class_source_code_from_blueprint("Order", structure_blueprint)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        imports_section = "\n".join(sorted(generator.imports))

        # Should use different class names for different domains
        assert "billing_customer: BillingCustomer = Field" in class_code
        assert "shipping_customer: Optional[ShippingCustomer]" in class_code
        assert "from billing.structures.customer import BillingCustomer" in imports_section
        assert "from shipping.structures.customer import ShippingCustomer" in imports_section
