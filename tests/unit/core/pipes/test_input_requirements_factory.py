import pytest

from pipelex.core.concepts.exceptions import ConceptCodeError
from pipelex.core.domains.exceptions import DomainError
from pipelex.core.pipes.input_requirements import InputRequirement
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory, InputRequirementsFactorySyntaxError
from pipelex.exceptions import ConceptLibraryConceptNotFoundError
from tests.unit.core.pipes.data import (
    CONCEPT_CODE_RESOLUTION_TEST_CASES,
    DIFFERENT_CONCEPT_CODES_TEST_CASES,
    EXPLICIT_DOMAIN_IN_STRING_TEST_CASES,
    FIXED_COUNT_TEST_CASES,
    MULTIPLE_ITEMS_EMPTY_BRACKETS_TEST_CASES,
    SINGLE_ITEM_NO_BRACKETS_TEST_CASES,
    VARIOUS_FIXED_COUNTS_TEST_CASES,
)


class TestMakeInputRequirementsFromString:
    """Test the InputRequirementsFactory.make_from_str method."""

    @pytest.mark.parametrize(
        ("domain", "requirement_str", "expected_concept_string", "expected_multiplicity"),
        SINGLE_ITEM_NO_BRACKETS_TEST_CASES,
    )
    def test_single_item_default_no_brackets(
        self, domain: str, requirement_str: str, expected_concept_string: str, expected_multiplicity: int | bool | None
    ):
        """Test parsing a concept string without brackets (single item, default)."""
        result = InputRequirementsFactory.make_from_string(domain=domain, requirement_str=requirement_str)

        assert isinstance(result, InputRequirement)
        assert result.concept.concept_string == expected_concept_string
        assert result.multiplicity == expected_multiplicity

    @pytest.mark.parametrize(
        ("domain", "requirement_str", "expected_concept_string"),
        MULTIPLE_ITEMS_EMPTY_BRACKETS_TEST_CASES,
    )
    def test_multiple_items_with_empty_brackets(self, domain: str, requirement_str: str, expected_concept_string: str):
        """Test parsing a concept string with empty brackets (multiple items)."""
        result = InputRequirementsFactory.make_from_string(domain=domain, requirement_str=requirement_str)

        assert isinstance(result, InputRequirement)
        assert result.concept.concept_string == expected_concept_string
        assert result.multiplicity is True

    @pytest.mark.parametrize(
        ("domain", "requirement_str", "expected_concept_string", "expected_multiplicity"),
        FIXED_COUNT_TEST_CASES,
    )
    def test_fixed_count_with_number_in_brackets(self, domain: str, requirement_str: str, expected_concept_string: str, expected_multiplicity: int):
        """Test parsing a concept string with a number in brackets (fixed count)."""
        result = InputRequirementsFactory.make_from_string(domain=domain, requirement_str=requirement_str)

        assert isinstance(result, InputRequirement)
        assert result.concept.concept_string == expected_concept_string
        assert result.multiplicity == expected_multiplicity

    @pytest.mark.parametrize(
        ("domain", "requirement_str", "expected_concept_string", "expected_multiplicity"),
        VARIOUS_FIXED_COUNTS_TEST_CASES,
    )
    def test_various_fixed_counts(self, domain: str, requirement_str: str, expected_concept_string: str, expected_multiplicity: int):
        """Test parsing concept strings with various numbers in brackets."""
        result = InputRequirementsFactory.make_from_string(domain=domain, requirement_str=requirement_str)
        assert result.multiplicity == expected_multiplicity, f"Failed for {requirement_str}"
        assert result.concept.concept_string == expected_concept_string

    @pytest.mark.parametrize(
        ("domain", "requirement_str", "expected_concept_string"),
        DIFFERENT_CONCEPT_CODES_TEST_CASES,
    )
    def test_different_concept_codes(self, domain: str, requirement_str: str, expected_concept_string: str):
        """Test parsing various concept codes without multiplicity."""
        result = InputRequirementsFactory.make_from_string(domain=domain, requirement_str=requirement_str)
        assert result.concept.concept_string == expected_concept_string
        assert result.multiplicity is None

    def test_custom_domain_concepts(self):
        """Test parsing concept codes from custom domains."""
        # Note: This test will only work if these concepts exist in the system
        # For now, we'll test with native concepts, but the pattern should work for any domain
        result = InputRequirementsFactory.make_from_string(domain="native", requirement_str="native.Text[3]")
        assert result.concept.concept_string == "native.Text"
        assert result.multiplicity == 3

    def test_concept_not_found_raises_error(self):
        """Test that an invalid concept code raises ConceptLibraryConceptNotFoundError."""
        with pytest.raises(ConceptLibraryConceptNotFoundError):
            InputRequirementsFactory.make_from_string(domain="nonexistent", requirement_str="nonexistent.InvalidConcept")

    def test_concept_not_found_with_multiplicity_raises_error(self):
        """Test that an invalid concept code with multiplicity raises ConceptLibraryConceptNotFoundError."""
        with pytest.raises(ConceptLibraryConceptNotFoundError):
            InputRequirementsFactory.make_from_string(domain="nonexistent", requirement_str="nonexistent.InvalidConcept[5]")

    def test_empty_string_raises_value_error(self):
        """Test that an empty string raises InputRequirementsFactorySyntaxError."""
        with pytest.raises(InputRequirementsFactorySyntaxError, match="Invalid input requirement string"):
            InputRequirementsFactory.make_from_string(domain="native", requirement_str="")

    def test_malformed_brackets_with_non_digit(self):
        """Test that brackets with non-digit content are treated as part of concept string."""
        # The regex will match "native.Text[abc]" as concept="native.Text[abc]", multiplicity=None
        # This will then fail during concept validation with ConceptCodeError
        with pytest.raises(ConceptCodeError):
            InputRequirementsFactory.make_from_string(domain="native", requirement_str="native.Text[abc]")

    def test_multiplicity_zero_in_brackets(self):
        """Test parsing a concept string with 0 in brackets."""
        result = InputRequirementsFactory.make_from_string(domain="native", requirement_str="native.Text[0]")

        assert isinstance(result, InputRequirement)
        assert result.concept.concept_string == "native.Text"
        assert result.multiplicity == 0

    def test_return_type(self):
        """Test that the method returns an InputRequirement instance."""
        result = InputRequirementsFactory.make_from_string(domain="native", requirement_str="native.Text")
        assert isinstance(result, InputRequirement)

    def test_concept_attribute_access(self):
        """Test that the returned InputRequirement has proper concept attributes."""
        result = InputRequirementsFactory.make_from_string(domain="native", requirement_str="native.Text[5]")

        assert hasattr(result, "concept")
        assert hasattr(result, "multiplicity")
        assert result.concept.concept_string == "native.Text"
        assert result.concept.code == "Text"

    def test_edge_case_very_long_number(self):
        """Test parsing with a very long number in brackets."""
        result = InputRequirementsFactory.make_from_string(domain="native", requirement_str="native.Text[999999]")

        assert result.multiplicity == 999999
        assert result.concept.concept_string == "native.Text"

    def test_whitespace_not_trimmed(self):
        """Test that whitespace is not automatically trimmed."""
        # Whitespace should cause domain validation to fail
        with pytest.raises(DomainError):
            InputRequirementsFactory.make_from_string(domain="native", requirement_str=" native.Text")

        # Trailing whitespace should cause concept code validation to fail
        with pytest.raises(ConceptCodeError):
            InputRequirementsFactory.make_from_string(domain="native", requirement_str="native.Text ")

    def test_multiple_brackets_treated_as_concept_name(self):
        """Test that multiple brackets are treated as part of the concept name."""
        # "native.Text[5][10]" should match as concept="native.Text[5]", multiplicity=10
        # This will fail during concept code validation
        with pytest.raises(ConceptCodeError):
            InputRequirementsFactory.make_from_string(domain="native", requirement_str="native.Text[5][10]")

    def test_brackets_at_start_treated_as_concept_name(self):
        """Test that brackets at the start are part of the concept name."""
        # This will fail during domain validation
        with pytest.raises(DomainError):
            InputRequirementsFactory.make_from_string(domain="native", requirement_str="[5]native.Text")

    @pytest.mark.parametrize(
        ("domain", "requirement_str", "concept_codes_from_same_domain", "expected_concept_string", "expected_multiplicity", "description"),
        CONCEPT_CODE_RESOLUTION_TEST_CASES,
    )
    def test_concept_code_resolution(
        self,
        domain: str,
        requirement_str: str,
        concept_codes_from_same_domain: list[str] | None,
        expected_concept_string: str,
        expected_multiplicity: int | bool | None,
        description: str,
    ):
        """Test that concept codes are resolved correctly with domain and concept_codes_from_same_domain.

        This tests:
        1. Native concepts are always recognized regardless of domain parameter
        2. Unknown concepts (not native, not in the domain) become implicit concepts
        3. concept_codes_from_same_domain helps resolve ambiguous concept codes
        """
        result = InputRequirementsFactory.make_from_string(
            domain=domain,
            requirement_str=requirement_str,
            concept_codes_from_the_same_domain=concept_codes_from_same_domain,
        )

        assert isinstance(result, InputRequirement)
        assert result.concept.concept_string == expected_concept_string, f"Failed: {description}"
        assert result.multiplicity == expected_multiplicity, f"Failed: {description}"

    @pytest.mark.parametrize(
        ("domain", "requirement_str", "expected_concept_string", "expected_multiplicity"),
        EXPLICIT_DOMAIN_IN_STRING_TEST_CASES,
    )
    def test_explicit_domain_in_string(
        self, domain: str, requirement_str: str, expected_concept_string: str, expected_multiplicity: int | bool | None
    ):
        """Test that explicitly specifying a domain in the requirement string works correctly."""
        result = InputRequirementsFactory.make_from_string(
            domain=domain,
            requirement_str=requirement_str,
        )

        assert isinstance(result, InputRequirement)
        assert result.concept.concept_string == expected_concept_string
        assert result.multiplicity == expected_multiplicity
