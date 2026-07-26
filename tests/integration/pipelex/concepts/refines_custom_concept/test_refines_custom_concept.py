"""Integration tests for refining custom concepts."""

from collections.abc import Callable
from pathlib import Path

from pipelex.core.concepts.concept import Concept
from pipelex.method_hub import get_library_manager


class TestRefinesCustomConcept:
    """Integration tests for concepts that refine custom concepts with structures."""

    def test_vip_customer_concept_loads_successfully(self, load_test_library: Callable[[list[Path]], None]):
        """Test that a concept refining a custom concept loads successfully."""
        # Load the test library from the current directory
        test_dir = Path(__file__).parent
        load_test_library([test_dir])

        library_manager = get_library_manager()
        library = library_manager.get_current_library()

        # Verify the base concept is loaded
        customer_concept = library.concept_library.get_required_concept("refines_custom_test.Customer")
        assert customer_concept is not None
        assert customer_concept.code == "Customer"
        assert customer_concept.domain_code == "refines_custom_test"

        # Verify the refined concept is loaded
        vip_customer_concept = library.concept_library.get_required_concept("refines_custom_test.VIPCustomer")
        assert vip_customer_concept is not None
        assert vip_customer_concept.code == "VIPCustomer"
        assert vip_customer_concept.domain_code == "refines_custom_test"
        assert vip_customer_concept.refines == "refines_custom_test.Customer"

    def test_vip_customer_inherits_structure_from_customer(self, load_test_library: Callable[[list[Path]], None]):
        """Test that VIPCustomer inherits the structure fields from Customer."""
        test_dir = Path(__file__).parent
        load_test_library([test_dir])

        library_manager = get_library_manager()
        library = library_manager.get_current_library()

        # Get both concepts
        customer_concept = library.concept_library.get_required_concept("refines_custom_test.Customer")
        vip_customer_concept = library.concept_library.get_required_concept("refines_custom_test.VIPCustomer")

        # Get the structure classes
        customer_class = customer_concept.get_structure_class()
        vip_customer_class = vip_customer_concept.get_structure_class()

        # Verify VIPCustomer is a subclass of Customer's structure class
        assert issubclass(vip_customer_class, customer_class)

        # Verify VIPCustomer has the fields from Customer
        customer_fields = set(customer_class.model_fields.keys())
        vip_customer_fields = set(vip_customer_class.model_fields.keys())

        # VIPCustomer should have at least all the fields that Customer has
        assert customer_fields.issubset(vip_customer_fields)

    def test_vip_customer_content_is_compatible_with_customer(self, load_test_library: Callable[[list[Path]], None]):
        """Test that VIPCustomer content can be used where Customer content is expected."""
        test_dir = Path(__file__).parent
        load_test_library([test_dir])

        library_manager = get_library_manager()
        library = library_manager.get_current_library()

        # Get concepts
        customer_concept = library.concept_library.get_required_concept("refines_custom_test.Customer")
        vip_customer_concept = library.concept_library.get_required_concept("refines_custom_test.VIPCustomer")

        # Get the structure classes
        customer_class = customer_concept.get_structure_class()
        vip_customer_class = vip_customer_concept.get_structure_class()

        # Create a VIPCustomer instance with Customer fields
        vip_customer_instance = vip_customer_class(
            name="John Doe",  # pyright: ignore[reportCallIssue]
            email="john@example.com",  # pyright: ignore[reportCallIssue]
        )

        # Verify it's an instance of the Customer class as well (due to inheritance)
        assert isinstance(vip_customer_instance, customer_class)

        # Verify fields are accessible
        assert vip_customer_instance.name == "John Doe"  # type: ignore[attr-defined]
        assert vip_customer_instance.email == "john@example.com"  # type: ignore[attr-defined]

    def test_concepts_are_compatible(self, load_test_library: Callable[[list[Path]], None]):
        """Test that Concept.are_concept_compatible returns True for refined concept."""
        test_dir = Path(__file__).parent
        load_test_library([test_dir])

        library_manager = get_library_manager()
        library = library_manager.get_current_library()

        # Get concepts
        customer_concept = library.concept_library.get_required_concept("refines_custom_test.Customer")
        vip_customer_concept = library.concept_library.get_required_concept("refines_custom_test.VIPCustomer")

        # VIPCustomer should be compatible with Customer (it refines Customer)
        assert Concept.are_concept_compatible(concept_1=vip_customer_concept, concept_2=customer_concept)
