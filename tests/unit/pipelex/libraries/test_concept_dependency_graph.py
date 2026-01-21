"""Tests for ConceptDependencyGraph utility for topological sorting of concept dependencies."""

import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import (
    ConceptStructureBlueprint,
    ConceptStructureBlueprintFieldType,
)
from pipelex.libraries.concept_dependency_graph import (
    ConceptDependencyGraph,
    CycleDetectedError,
)


class TestConceptDependencyGraph:
    """Test ConceptDependencyGraph for extracting dependencies and topological sorting."""

    def test_extract_dependencies_no_references(self):
        """Test extracting dependencies from a concept with no concept references."""
        blueprint = ConceptBlueprint(
            description="A simple concept",
            structure={
                "name": ConceptStructureBlueprint(
                    description="The name",
                    type=ConceptStructureBlueprintFieldType.TEXT,
                ),
                "age": ConceptStructureBlueprint(
                    description="The age",
                    type=ConceptStructureBlueprintFieldType.INTEGER,
                ),
            },
        )

        graph = ConceptDependencyGraph()
        dependencies = graph.extract_dependencies("myapp.Person", blueprint)

        assert dependencies == set()

    def test_extract_dependencies_single_concept_ref(self):
        """Test extracting dependencies from a concept with a single concept reference."""
        blueprint = ConceptBlueprint(
            description="An invoice with a customer",
            structure={
                "customer": ConceptStructureBlueprint(
                    description="The customer",
                    type=ConceptStructureBlueprintFieldType.CONCEPT,
                    concept_ref="myapp.Customer",
                ),
                "total": ConceptStructureBlueprint(
                    description="Invoice total",
                    type=ConceptStructureBlueprintFieldType.NUMBER,
                ),
            },
        )

        graph = ConceptDependencyGraph()
        dependencies = graph.extract_dependencies("myapp.Invoice", blueprint)

        assert dependencies == {"myapp.Customer"}

    def test_extract_dependencies_multiple_concept_refs(self):
        """Test extracting dependencies from a concept with multiple concept references."""
        blueprint = ConceptBlueprint(
            description="An order with customer and products",
            structure={
                "customer": ConceptStructureBlueprint(
                    description="The customer",
                    type=ConceptStructureBlueprintFieldType.CONCEPT,
                    concept_ref="myapp.Customer",
                ),
                "product": ConceptStructureBlueprint(
                    description="The product",
                    type=ConceptStructureBlueprintFieldType.CONCEPT,
                    concept_ref="myapp.Product",
                ),
            },
        )

        graph = ConceptDependencyGraph()
        dependencies = graph.extract_dependencies("myapp.Order", blueprint)

        assert dependencies == {"myapp.Customer", "myapp.Product"}

    def test_extract_dependencies_list_of_concepts(self):
        """Test extracting dependencies from a concept with list of concept references."""
        blueprint = ConceptBlueprint(
            description="An invoice with line items",
            structure={
                "items": ConceptStructureBlueprint(
                    description="Line items",
                    type=ConceptStructureBlueprintFieldType.LIST,
                    item_type="concept",
                    item_concept_ref="myapp.LineItem",
                ),
            },
        )

        graph = ConceptDependencyGraph()
        dependencies = graph.extract_dependencies("myapp.Invoice", blueprint)

        assert dependencies == {"myapp.LineItem"}

    def test_extract_dependencies_cross_domain(self):
        """Test extracting dependencies from a concept with cross-domain references."""
        blueprint = ConceptBlueprint(
            description="An invoice with CRM customer",
            structure={
                "customer": ConceptStructureBlueprint(
                    description="The customer",
                    type=ConceptStructureBlueprintFieldType.CONCEPT,
                    concept_ref="crm.Customer",
                ),
            },
        )

        graph = ConceptDependencyGraph()
        dependencies = graph.extract_dependencies("accounting.Invoice", blueprint)

        assert dependencies == {"crm.Customer"}

    def test_topological_sort_no_dependencies(self):
        """Test topological sort with concepts that have no dependencies."""
        blueprints = {
            "myapp.Customer": ConceptBlueprint(
                description="A customer",
                structure={
                    "name": ConceptStructureBlueprint(
                        description="Customer name",
                        type=ConceptStructureBlueprintFieldType.TEXT,
                    ),
                },
            ),
            "myapp.Product": ConceptBlueprint(
                description="A product",
                structure={
                    "name": ConceptStructureBlueprint(
                        description="Product name",
                        type=ConceptStructureBlueprintFieldType.TEXT,
                    ),
                },
            ),
        }

        graph = ConceptDependencyGraph()
        sorted_refs = graph.topological_sort(blueprints)

        # Both concepts have no dependencies, so order doesn't matter
        # but both should be in the result
        assert set(sorted_refs) == {"myapp.Customer", "myapp.Product"}

    def test_topological_sort_simple_dependency(self):
        """Test topological sort with a simple A -> B dependency."""
        blueprints = {
            "myapp.Customer": ConceptBlueprint(
                description="A customer",
                structure={
                    "name": ConceptStructureBlueprint(
                        description="Customer name",
                        type=ConceptStructureBlueprintFieldType.TEXT,
                    ),
                },
            ),
            "myapp.Invoice": ConceptBlueprint(
                description="An invoice",
                structure={
                    "customer": ConceptStructureBlueprint(
                        description="The customer",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.Customer",
                    ),
                },
            ),
        }

        graph = ConceptDependencyGraph()
        sorted_refs = graph.topological_sort(blueprints)

        # Customer must come before Invoice
        assert sorted_refs.index("myapp.Customer") < sorted_refs.index("myapp.Invoice")

    def test_topological_sort_chain_dependency(self):
        """Test topological sort with a chain A -> B -> C."""
        blueprints = {
            "myapp.Address": ConceptBlueprint(
                description="An address",
                structure={
                    "street": ConceptStructureBlueprint(
                        description="Street",
                        type=ConceptStructureBlueprintFieldType.TEXT,
                    ),
                },
            ),
            "myapp.Customer": ConceptBlueprint(
                description="A customer",
                structure={
                    "address": ConceptStructureBlueprint(
                        description="The address",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.Address",
                    ),
                },
            ),
            "myapp.Invoice": ConceptBlueprint(
                description="An invoice",
                structure={
                    "customer": ConceptStructureBlueprint(
                        description="The customer",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.Customer",
                    ),
                },
            ),
        }

        graph = ConceptDependencyGraph()
        sorted_refs = graph.topological_sort(blueprints)

        # Address must come before Customer, Customer must come before Invoice
        assert sorted_refs.index("myapp.Address") < sorted_refs.index("myapp.Customer")
        assert sorted_refs.index("myapp.Customer") < sorted_refs.index("myapp.Invoice")

    def test_topological_sort_diamond_dependency(self):
        """Test topological sort with a diamond pattern A -> B, A -> C, B -> D, C -> D."""
        blueprints = {
            "myapp.Base": ConceptBlueprint(
                description="Base concept",
                structure={
                    "id": ConceptStructureBlueprint(
                        description="ID",
                        type=ConceptStructureBlueprintFieldType.TEXT,
                    ),
                },
            ),
            "myapp.Left": ConceptBlueprint(
                description="Left concept",
                structure={
                    "base": ConceptStructureBlueprint(
                        description="Base ref",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.Base",
                    ),
                },
            ),
            "myapp.Right": ConceptBlueprint(
                description="Right concept",
                structure={
                    "base": ConceptStructureBlueprint(
                        description="Base ref",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.Base",
                    ),
                },
            ),
            "myapp.Top": ConceptBlueprint(
                description="Top concept",
                structure={
                    "left": ConceptStructureBlueprint(
                        description="Left ref",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.Left",
                    ),
                    "right": ConceptStructureBlueprint(
                        description="Right ref",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.Right",
                    ),
                },
            ),
        }

        graph = ConceptDependencyGraph()
        sorted_refs = graph.topological_sort(blueprints)

        # Base must come before Left and Right
        # Left and Right must come before Top
        base_idx = sorted_refs.index("myapp.Base")
        left_idx = sorted_refs.index("myapp.Left")
        right_idx = sorted_refs.index("myapp.Right")
        top_idx = sorted_refs.index("myapp.Top")

        assert base_idx < left_idx
        assert base_idx < right_idx
        assert left_idx < top_idx
        assert right_idx < top_idx

    def test_detect_simple_cycle(self):
        """Test cycle detection with a simple A -> B -> A cycle."""
        blueprints = {
            "myapp.A": ConceptBlueprint(
                description="Concept A",
                structure={
                    "b_ref": ConceptStructureBlueprint(
                        description="Reference to B",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.B",
                    ),
                },
            ),
            "myapp.B": ConceptBlueprint(
                description="Concept B",
                structure={
                    "a_ref": ConceptStructureBlueprint(
                        description="Reference to A",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.A",
                    ),
                },
            ),
        }

        graph = ConceptDependencyGraph()

        with pytest.raises(CycleDetectedError) as exc_info:
            graph.topological_sort(blueprints)

        # The error message should contain information about the cycle
        assert "cycle" in str(exc_info.value).lower()
        assert "myapp.A" in str(exc_info.value) or "myapp.B" in str(exc_info.value)

    def test_detect_self_reference_cycle(self):
        """Test cycle detection with a self-reference A -> A."""
        blueprints = {
            "myapp.Node": ConceptBlueprint(
                description="A node that references itself",
                structure={
                    "parent": ConceptStructureBlueprint(
                        description="Parent node",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.Node",
                    ),
                },
            ),
        }

        graph = ConceptDependencyGraph()

        with pytest.raises(CycleDetectedError) as exc_info:
            graph.topological_sort(blueprints)

        assert "cycle" in str(exc_info.value).lower()
        assert "myapp.Node" in str(exc_info.value)

    def test_detect_longer_cycle(self):
        """Test cycle detection with a longer A -> B -> C -> A cycle."""
        blueprints = {
            "myapp.A": ConceptBlueprint(
                description="Concept A",
                structure={
                    "b_ref": ConceptStructureBlueprint(
                        description="Reference to B",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.B",
                    ),
                },
            ),
            "myapp.B": ConceptBlueprint(
                description="Concept B",
                structure={
                    "c_ref": ConceptStructureBlueprint(
                        description="Reference to C",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.C",
                    ),
                },
            ),
            "myapp.C": ConceptBlueprint(
                description="Concept C",
                structure={
                    "a_ref": ConceptStructureBlueprint(
                        description="Reference to A",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.A",
                    ),
                },
            ),
        }

        graph = ConceptDependencyGraph()

        with pytest.raises(CycleDetectedError) as exc_info:
            graph.topological_sort(blueprints)

        assert "cycle" in str(exc_info.value).lower()

    def test_external_dependencies_not_in_graph(self):
        """Test that references to concepts not in the graph (e.g., native concepts) are handled."""
        blueprints = {
            "myapp.Customer": ConceptBlueprint(
                description="A customer that refines Text",
                refines="native.Text",
            ),
            "myapp.Invoice": ConceptBlueprint(
                description="An invoice",
                structure={
                    "customer": ConceptStructureBlueprint(
                        description="The customer",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.Customer",
                    ),
                },
            ),
        }

        graph = ConceptDependencyGraph()
        sorted_refs = graph.topological_sort(blueprints)

        # Customer must come before Invoice, native.Text is external and ignored
        assert sorted_refs.index("myapp.Customer") < sorted_refs.index("myapp.Invoice")

    def test_empty_blueprints(self):
        """Test topological sort with empty blueprints dict."""
        graph = ConceptDependencyGraph()
        sorted_refs = graph.topological_sort({})

        assert sorted_refs == []

    def test_concept_with_no_structure(self):
        """Test handling concepts that have no structure (e.g., string-based)."""
        blueprints = {
            "myapp.SimpleConcept": ConceptBlueprint(
                description="A simple concept with no structure",
            ),
            "myapp.Invoice": ConceptBlueprint(
                description="An invoice",
                structure={
                    "simple": ConceptStructureBlueprint(
                        description="The simple concept",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.SimpleConcept",
                    ),
                },
            ),
        }

        graph = ConceptDependencyGraph()
        sorted_refs = graph.topological_sort(blueprints)

        # SimpleConcept must come before Invoice
        assert sorted_refs.index("myapp.SimpleConcept") < sorted_refs.index("myapp.Invoice")

    # =========================================================================
    # Tests for refines dependencies
    # =========================================================================

    def test_extract_dependencies_from_refines(self):
        """Test extracting dependencies from the refines field."""
        blueprint = ConceptBlueprint(
            description="A customer that refines a base entity",
            refines="myapp.BaseEntity",
        )

        graph = ConceptDependencyGraph()
        dependencies = graph.extract_dependencies("myapp.Customer", blueprint)

        assert dependencies == {"myapp.BaseEntity"}

    def test_extract_dependencies_refines_native_not_included(self):
        """Test that native concept refs in refines are not included as dependencies."""
        blueprint = ConceptBlueprint(
            description="A customer that refines Text",
            refines="native.Text",
        )

        graph = ConceptDependencyGraph()
        dependencies = graph.extract_dependencies("myapp.Customer", blueprint)

        # Native concepts should not create dependencies
        assert dependencies == set()

    def test_extract_dependencies_refines_without_domain_not_included(self):
        """Test that native concept codes without domain are not included as dependencies."""
        blueprint = ConceptBlueprint(
            description="A customer that refines Text",
            refines="Text",  # Native code without domain prefix
        )

        graph = ConceptDependencyGraph()
        dependencies = graph.extract_dependencies("myapp.Customer", blueprint)

        # Native concepts (without dot) should not create dependencies
        assert dependencies == set()

    def test_topological_sort_simple_refines_dependency(self):
        """Test topological sort with a simple A refines B dependency."""
        blueprints = {
            "myapp.BaseEntity": ConceptBlueprint(
                description="A base entity",
                structure={
                    "id": ConceptStructureBlueprint(
                        description="Entity ID",
                        type=ConceptStructureBlueprintFieldType.TEXT,
                    ),
                },
            ),
            "myapp.Customer": ConceptBlueprint(
                description="A customer that refines BaseEntity",
                refines="myapp.BaseEntity",
            ),
        }

        graph = ConceptDependencyGraph()
        sorted_refs = graph.topological_sort(blueprints)

        # BaseEntity must come before Customer
        assert sorted_refs.index("myapp.BaseEntity") < sorted_refs.index("myapp.Customer")

    def test_topological_sort_multi_level_refines_chain(self):
        """Test topological sort with multi-level refines: A refines B refines C."""
        blueprints = {
            "myapp.Level1": ConceptBlueprint(
                description="Level 1 - base",
                structure={
                    "field1": ConceptStructureBlueprint(
                        description="Field 1",
                        type=ConceptStructureBlueprintFieldType.TEXT,
                    ),
                },
            ),
            "myapp.Level2": ConceptBlueprint(
                description="Level 2 - refines Level1",
                refines="myapp.Level1",
            ),
            "myapp.Level3": ConceptBlueprint(
                description="Level 3 - refines Level2",
                refines="myapp.Level2",
            ),
        }

        graph = ConceptDependencyGraph()
        sorted_refs = graph.topological_sort(blueprints)

        # Level1 < Level2 < Level3
        assert sorted_refs.index("myapp.Level1") < sorted_refs.index("myapp.Level2")
        assert sorted_refs.index("myapp.Level2") < sorted_refs.index("myapp.Level3")

    def test_topological_sort_deep_refines_chain(self):
        """Test topological sort with a deep 5-level refines chain."""
        blueprints = {
            "myapp.L1": ConceptBlueprint(
                description="Level 1",
                structure={
                    "id": ConceptStructureBlueprint(
                        description="ID",
                        type=ConceptStructureBlueprintFieldType.TEXT,
                    ),
                },
            ),
            "myapp.L2": ConceptBlueprint(
                description="Level 2",
                refines="myapp.L1",
            ),
            "myapp.L3": ConceptBlueprint(
                description="Level 3",
                refines="myapp.L2",
            ),
            "myapp.L4": ConceptBlueprint(
                description="Level 4",
                refines="myapp.L3",
            ),
            "myapp.L5": ConceptBlueprint(
                description="Level 5",
                refines="myapp.L4",
            ),
        }

        graph = ConceptDependencyGraph()
        sorted_refs = graph.topological_sort(blueprints)

        # L1 < L2 < L3 < L4 < L5
        for idx in range(1, 5):
            current = f"myapp.L{idx}"
            next_level = f"myapp.L{idx + 1}"
            assert sorted_refs.index(current) < sorted_refs.index(next_level), f"Expected {current} before {next_level}"

    def test_topological_sort_mixed_refines_and_concept_ref(self):
        """Test topological sort with both refines and concept_ref dependencies."""
        blueprints = {
            "myapp.Address": ConceptBlueprint(
                description="An address",
                structure={
                    "street": ConceptStructureBlueprint(
                        description="Street",
                        type=ConceptStructureBlueprintFieldType.TEXT,
                    ),
                },
            ),
            "myapp.BaseEntity": ConceptBlueprint(
                description="A base entity",
                structure={
                    "id": ConceptStructureBlueprint(
                        description="ID",
                        type=ConceptStructureBlueprintFieldType.TEXT,
                    ),
                },
            ),
            "myapp.Customer": ConceptBlueprint(
                description="A customer that refines BaseEntity and has an Address",
                refines="myapp.BaseEntity",
            ),
            "myapp.Order": ConceptBlueprint(
                description="An order with customer and shipping address",
                structure={
                    "customer": ConceptStructureBlueprint(
                        description="The customer",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.Customer",
                    ),
                    "shipping_address": ConceptStructureBlueprint(
                        description="Shipping address",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.Address",
                    ),
                },
            ),
        }

        graph = ConceptDependencyGraph()
        sorted_refs = graph.topological_sort(blueprints)

        # BaseEntity must come before Customer (refines)
        assert sorted_refs.index("myapp.BaseEntity") < sorted_refs.index("myapp.Customer")
        # Customer and Address must come before Order (concept_ref)
        assert sorted_refs.index("myapp.Customer") < sorted_refs.index("myapp.Order")
        assert sorted_refs.index("myapp.Address") < sorted_refs.index("myapp.Order")

    # =========================================================================
    # Tests for cycles in refines
    # =========================================================================

    def test_detect_refines_cycle(self):
        """Test cycle detection with A refines B refines A."""
        blueprints = {
            "myapp.A": ConceptBlueprint(
                description="Concept A refines B",
                refines="myapp.B",
            ),
            "myapp.B": ConceptBlueprint(
                description="Concept B refines A",
                refines="myapp.A",
            ),
        }

        graph = ConceptDependencyGraph()

        with pytest.raises(CycleDetectedError) as exc_info:
            graph.topological_sort(blueprints)

        assert "cycle" in str(exc_info.value).lower()

    def test_detect_longer_refines_cycle(self):
        """Test cycle detection with A refines B refines C refines A."""
        blueprints = {
            "myapp.A": ConceptBlueprint(
                description="Concept A refines B",
                refines="myapp.B",
            ),
            "myapp.B": ConceptBlueprint(
                description="Concept B refines C",
                refines="myapp.C",
            ),
            "myapp.C": ConceptBlueprint(
                description="Concept C refines A - creating a cycle",
                refines="myapp.A",
            ),
        }

        graph = ConceptDependencyGraph()

        with pytest.raises(CycleDetectedError) as exc_info:
            graph.topological_sort(blueprints)

        assert "cycle" in str(exc_info.value).lower()

    def test_detect_hidden_cycle_in_nested_refines(self):
        """Test cycle detection where cycle is hidden deep in a refines chain.

        Structure:
        - TopLevel has a concept_ref to MiddleLayer
        - MiddleLayer refines DeepLevel
        - DeepLevel has a concept_ref to Hidden
        - Hidden refines DeepLevel (cycle!)
        """
        blueprints = {
            "myapp.TopLevel": ConceptBlueprint(
                description="Top level concept",
                structure={
                    "middle": ConceptStructureBlueprint(
                        description="Middle layer reference",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.MiddleLayer",
                    ),
                },
            ),
            "myapp.MiddleLayer": ConceptBlueprint(
                description="Middle layer - refines DeepLevel",
                refines="myapp.DeepLevel",
            ),
            "myapp.DeepLevel": ConceptBlueprint(
                description="Deep level",
                structure={
                    "hidden": ConceptStructureBlueprint(
                        description="Hidden reference",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.Hidden",
                    ),
                },
            ),
            "myapp.Hidden": ConceptBlueprint(
                description="Hidden - refines DeepLevel creating a cycle",
                refines="myapp.DeepLevel",
            ),
        }

        graph = ConceptDependencyGraph()

        with pytest.raises(CycleDetectedError) as exc_info:
            graph.topological_sort(blueprints)

        assert "cycle" in str(exc_info.value).lower()

    def test_detect_cycle_mixed_refines_and_concept_ref(self):
        """Test cycle detection with mixed refines and concept_ref creating a cycle.

        Structure:
        - A refines B
        - B has concept_ref to C
        - C refines A (cycle!)
        """
        blueprints = {
            "myapp.A": ConceptBlueprint(
                description="Concept A refines B",
                refines="myapp.B",
            ),
            "myapp.B": ConceptBlueprint(
                description="Concept B has concept_ref to C",
                structure={
                    "c_ref": ConceptStructureBlueprint(
                        description="Reference to C",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.C",
                    ),
                },
            ),
            "myapp.C": ConceptBlueprint(
                description="Concept C refines A - creating a cycle",
                refines="myapp.A",
            ),
        }

        graph = ConceptDependencyGraph()

        with pytest.raises(CycleDetectedError) as exc_info:
            graph.topological_sort(blueprints)

        assert "cycle" in str(exc_info.value).lower()

    def test_detect_deeply_hidden_cycle(self):
        """Test cycle detection where cycle is hidden 5 levels deep.

        Structure:
        - A refines B
        - B refines C
        - C refines D
        - D refines E
        - E refines A (cycle!)
        """
        blueprints = {
            "myapp.A": ConceptBlueprint(
                description="A refines B",
                refines="myapp.B",
            ),
            "myapp.B": ConceptBlueprint(
                description="B refines C",
                refines="myapp.C",
            ),
            "myapp.C": ConceptBlueprint(
                description="C refines D",
                refines="myapp.D",
            ),
            "myapp.D": ConceptBlueprint(
                description="D refines E",
                refines="myapp.E",
            ),
            "myapp.E": ConceptBlueprint(
                description="E refines A - deeply hidden cycle",
                refines="myapp.A",
            ),
        }

        graph = ConceptDependencyGraph()

        with pytest.raises(CycleDetectedError) as exc_info:
            graph.topological_sort(blueprints)

        assert "cycle" in str(exc_info.value).lower()

    def test_detect_cycle_hidden_in_nested_list_concept_refs(self):
        """Test cycle detection hidden in nested list of concept refs.

        Structure:
        - Parent has a list of Items
        - Item refines BaseItem
        - BaseItem has a concept_ref back to Parent (cycle!)
        """
        blueprints = {
            "myapp.Parent": ConceptBlueprint(
                description="Parent with list of items",
                structure={
                    "items": ConceptStructureBlueprint(
                        description="List of items",
                        type=ConceptStructureBlueprintFieldType.LIST,
                        item_type="concept",
                        item_concept_ref="myapp.Item",
                    ),
                },
            ),
            "myapp.Item": ConceptBlueprint(
                description="Item refines BaseItem",
                refines="myapp.BaseItem",
            ),
            "myapp.BaseItem": ConceptBlueprint(
                description="BaseItem with parent reference - cycle",
                structure={
                    "parent": ConceptStructureBlueprint(
                        description="Parent reference",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.Parent",
                    ),
                },
            ),
        }

        graph = ConceptDependencyGraph()

        with pytest.raises(CycleDetectedError) as exc_info:
            graph.topological_sort(blueprints)

        assert "cycle" in str(exc_info.value).lower()

    def test_no_cycle_when_refines_native(self):
        """Test that refining native concepts doesn't create false cycle detection."""
        blueprints = {
            "myapp.TextDoc": ConceptBlueprint(
                description="A text document that refines native.Text",
                refines="native.Text",
            ),
            "myapp.Report": ConceptBlueprint(
                description="A report that references TextDoc",
                structure={
                    "content": ConceptStructureBlueprint(
                        description="The content",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="myapp.TextDoc",
                    ),
                },
            ),
            "myapp.Summary": ConceptBlueprint(
                description="A summary that refines native.Text",
                refines="native.Text",
            ),
        }

        graph = ConceptDependencyGraph()
        sorted_refs = graph.topological_sort(blueprints)

        # TextDoc must come before Report
        assert sorted_refs.index("myapp.TextDoc") < sorted_refs.index("myapp.Report")
        # All three should be in the result
        assert set(sorted_refs) == {"myapp.TextDoc", "myapp.Report", "myapp.Summary"}

    def test_cross_domain_refines_dependency(self):
        """Test that cross-domain refines creates proper dependency."""
        blueprints = {
            "core.BaseEntity": ConceptBlueprint(
                description="Base entity in core domain",
                structure={
                    "id": ConceptStructureBlueprint(
                        description="Entity ID",
                        type=ConceptStructureBlueprintFieldType.TEXT,
                    ),
                },
            ),
            "crm.Customer": ConceptBlueprint(
                description="Customer refining core.BaseEntity",
                refines="core.BaseEntity",
            ),
            "sales.Order": ConceptBlueprint(
                description="Order with customer reference",
                structure={
                    "customer": ConceptStructureBlueprint(
                        description="Customer",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="crm.Customer",
                    ),
                },
            ),
        }

        graph = ConceptDependencyGraph()
        sorted_refs = graph.topological_sort(blueprints)

        # core.BaseEntity < crm.Customer < sales.Order
        assert sorted_refs.index("core.BaseEntity") < sorted_refs.index("crm.Customer")
        assert sorted_refs.index("crm.Customer") < sorted_refs.index("sales.Order")
