import pytest

from pipelex.core.concepts.exceptions import ConceptCodeError
from pipelex.core.domains.exceptions import DomainError
from pipelex.core.pipes.input_requirements import InputRequirement
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory, InputRequirementsFactorySyntaxError
from pipelex.exceptions import ConceptLibraryConceptNotFoundError


class TestMakeInputRequirementsFromString:
    """Test the InputRequirementsFactory.make_from_str method."""

    def test_single_item_default_no_brackets(self):
        """Test parsing a concept string without brackets (single item, default)."""
        result = InputRequirementsFactory.make_from_string("native.Text")

        assert isinstance(result, InputRequirement)
        assert result.concept.concept_string == "native.Text"
        assert result.multiplicity is None

    def test_multiple_items_with_empty_brackets(self):
        """Test parsing a concept string with empty brackets (multiple items)."""
        result = InputRequirementsFactory.make_from_string("native.Text[]")

        assert isinstance(result, InputRequirement)
        assert result.concept.concept_string == "native.Text"
        assert result.multiplicity is True

    def test_fixed_count_with_number_in_brackets(self):
        """Test parsing a concept string with a number in brackets (fixed count)."""
        result = InputRequirementsFactory.make_from_string("native.Text[5]")

        assert isinstance(result, InputRequirement)
        assert result.concept.concept_string == "native.Text"
        assert result.multiplicity == 5

    def test_various_fixed_counts(self):
        """Test parsing concept strings with various numbers in brackets."""
        test_cases = [
            ("native.Image[1]", 1),
            ("native.Image[2]", 2),
            ("native.Image[10]", 10),
            ("native.Image[100]", 100),
            ("native.Image[999]", 999),
        ]

        for requirement_str, expected_multiplicity in test_cases:
            result = InputRequirementsFactory.make_from_string(requirement_str)
            assert result.multiplicity == expected_multiplicity, f"Failed for {requirement_str}"
            assert result.concept.concept_string == "native.Image"

    def test_different_concept_codes(self):
        """Test parsing various concept codes without multiplicity."""
        test_cases = [
            "native.Text",
            "native.Image",
            "native.PDF",
            "native.Number",
            "native.Page",
        ]

        for concept_code in test_cases:
            result = InputRequirementsFactory.make_from_string(concept_code)
            assert result.concept.concept_string == concept_code
            assert result.multiplicity is None

    def test_custom_domain_concepts(self):
        """Test parsing concept codes from custom domains."""
        # Note: This test will only work if these concepts exist in the system
        # For now, we'll test with native concepts, but the pattern should work for any domain
        result = InputRequirementsFactory.make_from_string("native.Text[3]")
        assert result.concept.concept_string == "native.Text"
        assert result.multiplicity == 3

    def test_concept_not_found_raises_error(self):
        """Test that an invalid concept code raises ConceptLibraryConceptNotFoundError."""
        with pytest.raises(ConceptLibraryConceptNotFoundError):
            InputRequirementsFactory.make_from_string("nonexistent.InvalidConcept")

    def test_concept_not_found_with_multiplicity_raises_error(self):
        """Test that an invalid concept code with multiplicity raises ConceptLibraryConceptNotFoundError."""
        with pytest.raises(ConceptLibraryConceptNotFoundError):
            InputRequirementsFactory.make_from_string("nonexistent.InvalidConcept[5]")

    def test_empty_string_raises_value_error(self):
        """Test that an empty string raises InputRequirementsFactorySyntaxError."""
        with pytest.raises(InputRequirementsFactorySyntaxError, match="Invalid input requirement string"):
            InputRequirementsFactory.make_from_string("")

    def test_malformed_brackets_with_non_digit(self):
        """Test that brackets with non-digit content are treated as part of concept string."""
        # The regex will match "native.Text[abc]" as concept="native.Text[abc]", multiplicity=None
        # This will then fail during concept validation with ConceptCodeError
        with pytest.raises(ConceptCodeError):
            InputRequirementsFactory.make_from_string("native.Text[abc]")

    def test_multiplicity_zero_in_brackets(self):
        """Test parsing a concept string with 0 in brackets."""
        result = InputRequirementsFactory.make_from_string("native.Text[0]")

        assert isinstance(result, InputRequirement)
        assert result.concept.concept_string == "native.Text"
        assert result.multiplicity == 0

    def test_return_type(self):
        """Test that the method returns an InputRequirement instance."""
        result = InputRequirementsFactory.make_from_string("native.Text")
        assert isinstance(result, InputRequirement)

    def test_concept_attribute_access(self):
        """Test that the returned InputRequirement has proper concept attributes."""
        result = InputRequirementsFactory.make_from_string("native.Text[5]")

        assert hasattr(result, "concept")
        assert hasattr(result, "multiplicity")
        assert result.concept.concept_string == "native.Text"
        assert result.concept.code == "Text"

    def test_edge_case_very_long_number(self):
        """Test parsing with a very long number in brackets."""
        result = InputRequirementsFactory.make_from_string("native.Text[999999]")

        assert result.multiplicity == 999999
        assert result.concept.concept_string == "native.Text"

    def test_whitespace_not_trimmed(self):
        """Test that whitespace is not automatically trimmed."""
        # Whitespace should cause domain validation to fail
        with pytest.raises(DomainError):
            InputRequirementsFactory.make_from_string(" native.Text")

        # Trailing whitespace should cause concept code validation to fail
        with pytest.raises(ConceptCodeError):
            InputRequirementsFactory.make_from_string("native.Text ")

    def test_multiple_brackets_treated_as_concept_name(self):
        """Test that multiple brackets are treated as part of the concept name."""
        # "native.Text[5][10]" should match as concept="native.Text[5]", multiplicity=10
        # This will fail during concept code validation
        with pytest.raises(ConceptCodeError):
            InputRequirementsFactory.make_from_string("native.Text[5][10]")

    def test_brackets_at_start_treated_as_concept_name(self):
        """Test that brackets at the start are part of the concept name."""
        # This will fail during domain validation
        with pytest.raises(DomainError):
            InputRequirementsFactory.make_from_string("[5]native.Text")
