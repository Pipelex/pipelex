"""Integration tests for concept-to-concept references in MTHDS files."""

import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

from pipelex.interpreter_hub import get_concept_library, get_library_manager


class TestConceptToConceptReferences:
    """Integration tests for loading concepts with concept-to-concept references."""

    def test_load_concepts_with_single_reference(self, load_test_library: Callable[[list[Path]], None]):
        """Test loading concepts where one concept references another."""
        # Create a temporary MTHDS file with concept references
        mthds_content = """
domain = "testapp"
description = "Test domain for concept references"

[concept.Customer]
description = "A customer"

[concept.Customer.structure]
name = { type = "text", description = "Customer name" }
email = { type = "text", description = "Customer email" }

[concept.Invoice]
description = "An invoice with a customer reference"

[concept.Invoice.structure]
customer = { type = "concept", concept_ref = "testapp.Customer", description = "The customer" }
total = { type = "number", description = "Invoice total" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test_concepts.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            load_test_library([Path(tmp_dir)])

            library_manager = get_library_manager()
            library = library_manager.get_current_library()

            # Verify both concepts are loaded
            customer_concept = library.concept_library.get_required_concept("testapp.Customer")
            invoice_concept = library.concept_library.get_required_concept("testapp.Invoice")

            assert customer_concept is not None
            assert invoice_concept is not None

            # Verify the Invoice structure class has a customer field typed to Customer
            invoice_class = get_concept_library().get_structure_class(concept=invoice_concept)
            assert invoice_class is not None

            # The customer field should reference the Customer class
            customer_field = invoice_class.model_fields.get("customer")
            assert customer_field is not None

    def test_load_concepts_with_list_of_references(self, load_test_library: Callable[[list[Path]], None]):
        """Test loading concepts where one concept has a list of references to another."""
        mthds_content = """
domain = "testapp"
description = "Test domain for list of concept references"

[concept.LineItem]
description = "A line item"

[concept.LineItem.structure]
product = { type = "text", description = "Product name" }
quantity = { type = "integer", description = "Quantity" }
price = { type = "number", description = "Price" }

[concept.Invoice]
description = "An invoice with line items"

[concept.Invoice.structure]
items = { type = "list", item_type = "concept", item_concept_ref = "testapp.LineItem", description = "Line items" }
total = { type = "number", description = "Invoice total" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test_concepts.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            load_test_library([Path(tmp_dir)])

            library_manager = get_library_manager()
            library = library_manager.get_current_library()

            # Verify both concepts are loaded
            line_item_concept = library.concept_library.get_required_concept("testapp.LineItem")
            invoice_concept = library.concept_library.get_required_concept("testapp.Invoice")

            assert line_item_concept is not None
            assert invoice_concept is not None

            # Verify the Invoice structure class has an items field that's a list
            invoice_class = get_concept_library().get_structure_class(concept=invoice_concept)
            items_field = invoice_class.model_fields.get("items")
            assert items_field is not None

    def test_load_concepts_dependency_order(self, load_test_library: Callable[[list[Path]], None]):
        """Test that concepts are loaded in dependency order (dependencies first)."""
        # Define concepts in reverse dependency order in the MTHDS file
        mthds_content = """
domain = "testapp"
description = "Test domain for dependency ordering"

# Invoice depends on Customer, but defined first
[concept.Invoice]
description = "An invoice"

[concept.Invoice.structure]
customer = { type = "concept", concept_ref = "testapp.Customer", description = "The customer" }

# Customer is defined second but should be loaded first
[concept.Customer]
description = "A customer"

[concept.Customer.structure]
name = { type = "text", description = "Customer name" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test_concepts.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            # This should not raise an error - Customer should be loaded before Invoice
            load_test_library([Path(tmp_dir)])

            library_manager = get_library_manager()
            library = library_manager.get_current_library()

            # Verify both concepts are loaded correctly
            customer_concept = library.concept_library.get_required_concept("testapp.Customer")
            invoice_concept = library.concept_library.get_required_concept("testapp.Invoice")

            assert customer_concept is not None
            assert invoice_concept is not None

    def test_load_concepts_chain_dependencies(self, load_test_library: Callable[[list[Path]], None]):
        """Test loading concepts with chain dependencies: A -> B -> C."""
        mthds_content = """
domain = "testapp"
description = "Test domain for chain dependencies"

# Define in reverse order to test topological sort
[concept.Invoice]
description = "An invoice"

[concept.Invoice.structure]
customer = { type = "concept", concept_ref = "testapp.Customer", description = "The customer" }

[concept.Customer]
description = "A customer"

[concept.Customer.structure]
address = { type = "concept", concept_ref = "testapp.Address", description = "The address" }

[concept.Address]
description = "An address"

[concept.Address.structure]
street = { type = "text", description = "Street" }
city = { type = "text", description = "City" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test_concepts.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            load_test_library([Path(tmp_dir)])

            library_manager = get_library_manager()
            library = library_manager.get_current_library()

            # Verify all concepts are loaded
            address_concept = library.concept_library.get_required_concept("testapp.Address")
            customer_concept = library.concept_library.get_required_concept("testapp.Customer")
            invoice_concept = library.concept_library.get_required_concept("testapp.Invoice")

            assert address_concept is not None
            assert customer_concept is not None
            assert invoice_concept is not None

    def test_cycle_detection_raises_error(self, load_empty_library: Callable[[], str]):
        """Test that cyclic dependencies are detected and raise an error."""
        mthds_content = """
domain = "testapp"
description = "Test domain with cyclic dependencies"

[concept.A]
description = "Concept A references B"

[concept.A.structure]
b_ref = { type = "concept", concept_ref = "testapp.B", description = "Reference to B" }

[concept.B]
description = "Concept B references A - creating a cycle"

[concept.B.structure]
a_ref = { type = "concept", concept_ref = "testapp.A", description = "Reference to A" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test_concepts.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            library_id = load_empty_library()
            library_manager = get_library_manager()

            # Loading should raise an error due to cyclic dependency
            with pytest.raises(Exception, match=r"[Cc]ycle"):
                library_manager.load_libraries(
                    library_id=library_id,
                    library_dirs=[Path(tmp_dir)],
                )

    def test_cycle_detection_self_reference(self, load_empty_library: Callable[[], str]):
        """Test that a concept referencing itself is detected as a cycle."""
        mthds_content = """
domain = "testapp"
description = "Test domain with self-referencing concept"

[concept.Node]
description = "A node that references itself"

[concept.Node.structure]
name = { type = "text", description = "Node name" }
parent = { type = "concept", concept_ref = "testapp.Node", description = "Parent node" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test_concepts.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            library_id = load_empty_library()
            library_manager = get_library_manager()

            with pytest.raises(Exception, match=r"[Cc]ycle"):
                library_manager.load_libraries(
                    library_id=library_id,
                    library_dirs=[Path(tmp_dir)],
                )

    def test_cycle_detection_three_concepts(self, load_empty_library: Callable[[], str]):
        """Test that a cycle through three concepts (A -> B -> C -> A) is detected."""
        mthds_content = """
domain = "testapp"
description = "Test domain with three-concept cycle"

[concept.A]
description = "Concept A references B"

[concept.A.structure]
b_ref = { type = "concept", concept_ref = "testapp.B", description = "Reference to B" }

[concept.B]
description = "Concept B references C"

[concept.B.structure]
c_ref = { type = "concept", concept_ref = "testapp.C", description = "Reference to C" }

[concept.C]
description = "Concept C references A - completing the cycle"

[concept.C.structure]
a_ref = { type = "concept", concept_ref = "testapp.A", description = "Reference to A" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test_concepts.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            library_id = load_empty_library()
            library_manager = get_library_manager()

            with pytest.raises(Exception, match=r"[Cc]ycle"):
                library_manager.load_libraries(
                    library_id=library_id,
                    library_dirs=[Path(tmp_dir)],
                )

    def test_cycle_detection_long_chain(self, load_empty_library: Callable[[], str]):
        """Test that a cycle through many concepts (A -> B -> C -> D -> E -> A) is detected."""
        mthds_content = """
domain = "testapp"
description = "Test domain with long chain cycle"

[concept.A]
description = "Concept A"
[concept.A.structure]
next = { type = "concept", concept_ref = "testapp.B", description = "Next" }

[concept.B]
description = "Concept B"
[concept.B.structure]
next = { type = "concept", concept_ref = "testapp.C", description = "Next" }

[concept.C]
description = "Concept C"
[concept.C.structure]
next = { type = "concept", concept_ref = "testapp.D", description = "Next" }

[concept.D]
description = "Concept D"
[concept.D.structure]
next = { type = "concept", concept_ref = "testapp.E", description = "Next" }

[concept.E]
description = "Concept E - cycles back to A"
[concept.E.structure]
next = { type = "concept", concept_ref = "testapp.A", description = "Back to A" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test_concepts.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            library_id = load_empty_library()
            library_manager = get_library_manager()

            with pytest.raises(Exception, match=r"[Cc]ycle"):
                library_manager.load_libraries(
                    library_id=library_id,
                    library_dirs=[Path(tmp_dir)],
                )

    def test_cycle_detection_through_list_field(self, load_empty_library: Callable[[], str]):
        """Test that cycles through list fields are detected."""
        mthds_content = """
domain = "testapp"
description = "Test domain with cycle through list field"

[concept.Parent]
description = "A parent with children"

[concept.Parent.structure]
name = { type = "text", description = "Parent name" }
children = { type = "list", item_type = "concept", item_concept_ref = "testapp.Child", description = "Children" }

[concept.Child]
description = "A child that references back to parent"

[concept.Child.structure]
name = { type = "text", description = "Child name" }
parent = { type = "concept", concept_ref = "testapp.Parent", description = "Reference back to parent" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test_concepts.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            library_id = load_empty_library()
            library_manager = get_library_manager()

            with pytest.raises(Exception, match=r"[Cc]ycle"):
                library_manager.load_libraries(
                    library_id=library_id,
                    library_dirs=[Path(tmp_dir)],
                )

    def test_cycle_detection_partial_cycle_in_graph(self, load_empty_library: Callable[[], str]):
        """Test cycle detection when cycle is not at the start (D -> E -> F -> D, with A -> B -> C -> D)."""
        mthds_content = """
domain = "testapp"
description = "Test domain with cycle deeper in the graph"

[concept.A]
description = "Entry point"
[concept.A.structure]
next = { type = "concept", concept_ref = "testapp.B", description = "To B" }

[concept.B]
description = "Intermediate"
[concept.B.structure]
next = { type = "concept", concept_ref = "testapp.C", description = "To C" }

[concept.C]
description = "Leads to cycle"
[concept.C.structure]
next = { type = "concept", concept_ref = "testapp.D", description = "To D" }

[concept.D]
description = "Start of cycle"
[concept.D.structure]
next = { type = "concept", concept_ref = "testapp.E", description = "To E" }

[concept.E]
description = "Middle of cycle"
[concept.E.structure]
next = { type = "concept", concept_ref = "testapp.F", description = "To F" }

[concept.F]
description = "Completes cycle back to D"
[concept.F.structure]
next = { type = "concept", concept_ref = "testapp.D", description = "Back to D" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            mthds_path = Path(tmp_dir) / "test_concepts.mthds"
            mthds_path.write_text(mthds_content, encoding="utf-8")

            library_id = load_empty_library()
            library_manager = get_library_manager()

            with pytest.raises(Exception, match=r"[Cc]ycle"):
                library_manager.load_libraries(
                    library_id=library_id,
                    library_dirs=[Path(tmp_dir)],
                )

    def test_cross_domain_concept_reference(self, load_test_library: Callable[[list[Path]], None]):
        """Test loading concepts with cross-domain references."""
        crm_mthds = """
domain = "crm"
description = "CRM domain"

[concept.Customer]
description = "A CRM customer"

[concept.Customer.structure]
name = { type = "text", description = "Customer name" }
"""

        accounting_mthds = """
domain = "accounting"
description = "Accounting domain"

[concept.Invoice]
description = "An accounting invoice"

[concept.Invoice.structure]
customer = { type = "concept", concept_ref = "crm.Customer", description = "The CRM customer" }
amount = { type = "number", description = "Invoice amount" }
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            crm_path = Path(tmp_dir) / "crm.mthds"
            crm_path.write_text(crm_mthds, encoding="utf-8")

            accounting_path = Path(tmp_dir) / "accounting.mthds"
            accounting_path.write_text(accounting_mthds, encoding="utf-8")

            load_test_library([Path(tmp_dir)])

            library_manager = get_library_manager()
            library = library_manager.get_current_library()

            # Verify concepts from both domains are loaded
            customer_concept = library.concept_library.get_required_concept("crm.Customer")
            invoice_concept = library.concept_library.get_required_concept("accounting.Invoice")

            assert customer_concept is not None
            assert invoice_concept is not None
