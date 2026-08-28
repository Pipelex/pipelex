from typing import Callable

import pytest

from pipelex.core.concepts.exceptions import ConceptStringError
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory, InputStuffSpecsFactoryError
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import PresenceMarker
from pipelex.interpreter_hub import get_concept_library
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from tests.unit.pipelex.core.pipes.data import (
    CONCEPT_CODE_RESOLUTION_TEST_CASES,
    DIFFERENT_CONCEPT_CODES_TEST_CASES,
    EXPLICIT_DOMAIN_IN_STRING_TEST_CASES,
    FIXED_COUNT_TEST_CASES,
    MULTIPLE_ITEMS_EMPTY_BRACKETS_TEST_CASES,
    SINGLE_ITEM_NO_BRACKETS_TEST_CASES,
    VARIOUS_FIXED_COUNTS_TEST_CASES,
)


class TestMakeInputRequirementsFromString:
    """Test the InputStuffSpecsFactory.make_from_str method."""

    @pytest.mark.parametrize(
        ("domain_code", "stuff_spec_str", "expected_concept_ref", "expected_multiplicity"),
        SINGLE_ITEM_NO_BRACKETS_TEST_CASES,
    )
    def test_single_item_default_no_brackets(
        self,
        domain_code: str,
        stuff_spec_str: str,
        expected_concept_ref: str,
        expected_multiplicity: int | bool | None,
        load_empty_library: Callable[[], None],
    ):
        """Test parsing a concept string without brackets (single item, default)."""
        load_empty_library()
        result = InputStuffSpecsFactory.make_from_string(
            domain_code=domain_code, stuff_spec_str=stuff_spec_str, concept_provider=get_concept_library()
        )

        assert isinstance(result, StuffSpec)
        assert result.concept.concept_ref == expected_concept_ref
        assert result.multiplicity == expected_multiplicity

    @pytest.mark.parametrize(
        ("domain_code", "stuff_spec_str", "expected_concept_ref"),
        MULTIPLE_ITEMS_EMPTY_BRACKETS_TEST_CASES,
    )
    def test_multiple_items_with_empty_brackets(
        self, domain_code: str, stuff_spec_str: str, expected_concept_ref: str, load_empty_library: Callable[[], None]
    ):
        load_empty_library()
        """Test parsing a concept string with empty brackets (multiple items)."""
        result = InputStuffSpecsFactory.make_from_string(
            domain_code=domain_code, stuff_spec_str=stuff_spec_str, concept_provider=get_concept_library()
        )

        assert isinstance(result, StuffSpec)
        assert result.concept.concept_ref == expected_concept_ref
        assert result.multiplicity is True

    @pytest.mark.parametrize(
        ("domain_code", "stuff_spec_str", "expected_concept_ref", "expected_multiplicity"),
        FIXED_COUNT_TEST_CASES,
    )
    def test_fixed_count_with_number_in_brackets(
        self, domain_code: str, stuff_spec_str: str, expected_concept_ref: str, expected_multiplicity: int, load_empty_library: Callable[[], None]
    ):
        """Test parsing a concept string with a number in brackets (fixed count)."""
        load_empty_library()
        result = InputStuffSpecsFactory.make_from_string(
            domain_code=domain_code, stuff_spec_str=stuff_spec_str, concept_provider=get_concept_library()
        )

        assert isinstance(result, StuffSpec)
        assert result.concept.concept_ref == expected_concept_ref
        assert result.multiplicity == expected_multiplicity

    @pytest.mark.parametrize(
        ("domain_code", "stuff_spec_str", "expected_concept_ref", "expected_multiplicity"),
        VARIOUS_FIXED_COUNTS_TEST_CASES,
    )
    def test_various_fixed_counts(
        self, domain_code: str, stuff_spec_str: str, expected_concept_ref: str, expected_multiplicity: int, load_empty_library: Callable[[], None]
    ):
        load_empty_library()
        """Test parsing concept strings with various numbers in brackets."""
        result = InputStuffSpecsFactory.make_from_string(
            domain_code=domain_code, stuff_spec_str=stuff_spec_str, concept_provider=get_concept_library()
        )
        assert result.multiplicity == expected_multiplicity, f"Failed for {stuff_spec_str}"
        assert result.concept.concept_ref == expected_concept_ref

    def test_fixed_count_of_one_is_the_single_form(self, load_empty_library: Callable[[], None]):
        """`Concept[1]` builds a single-item spec, exactly as a bare `Concept` does.

        This factory parses input specs with its own regex rather than the shared parser, so it is the
        second place the `[1]`-is-single ruling has to hold — and the one the memory shaper reads.
        """
        load_empty_library()
        result = InputStuffSpecsFactory.make_from_string(
            domain_code="native", stuff_spec_str="native.Image[1]", concept_provider=get_concept_library()
        )
        assert result.concept.concept_ref == "native.Image"
        assert result.multiplicity is None
        assert result.is_multiple() is False

    @pytest.mark.parametrize(
        ("domain_code", "stuff_spec_str", "expected_concept_ref"),
        DIFFERENT_CONCEPT_CODES_TEST_CASES,
    )
    def test_different_concept_codes(self, domain_code: str, stuff_spec_str: str, expected_concept_ref: str, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test parsing various concept codes without multiplicity."""
        result = InputStuffSpecsFactory.make_from_string(
            domain_code=domain_code, stuff_spec_str=stuff_spec_str, concept_provider=get_concept_library()
        )
        assert result.concept.concept_ref == expected_concept_ref
        assert result.multiplicity is None

    def test_custom_domain_concepts(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test parsing concept codes from custom domains."""
        # Note: This test will only work if these concepts exist in the system
        # For now, we'll test with native concepts, but the pattern should work for any domain
        result = InputStuffSpecsFactory.make_from_string(
            domain_code="native", stuff_spec_str="native.Text[3]", concept_provider=get_concept_library()
        )
        assert result.concept.concept_ref == "native.Text"
        assert result.multiplicity == 3

    @pytest.mark.parametrize(
        ("stuff_spec_str", "expected_presence", "expected_multiplicity"),
        [
            ("native.Text", PresenceMarker.PLAIN, None),
            ("native.Text?", PresenceMarker.OPTIONAL, None),
            ("native.Text!", PresenceMarker.FORCE, None),
        ],
    )
    def test_presence_markers(
        self,
        stuff_spec_str: str,
        expected_presence: PresenceMarker,
        expected_multiplicity: int | bool | None,
        load_empty_library: Callable[[], None],
    ):
        """Test parsing presence markers on input stuff spec strings."""
        load_empty_library()
        result = InputStuffSpecsFactory.make_from_string(domain_code="native", stuff_spec_str=stuff_spec_str, concept_provider=get_concept_library())
        assert result.concept.concept_ref == "native.Text"
        assert result.multiplicity == expected_multiplicity
        assert result.presence == expected_presence

    def test_concept_not_found_raises_error(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test that an invalid concept code raises ConceptLibraryConceptNotFoundError."""
        with pytest.raises(ConceptLibraryError):
            InputStuffSpecsFactory.make_from_string(
                domain_code="nonexistent", stuff_spec_str="nonexistent.InvalidConcept", concept_provider=get_concept_library()
            )

    def test_concept_not_found_with_multiplicity_raises_error(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test that an invalid concept code with multiplicity raises ConceptLibraryConceptNotFoundError."""
        with pytest.raises(ConceptLibraryError):
            InputStuffSpecsFactory.make_from_string(
                domain_code="nonexistent", stuff_spec_str="nonexistent.InvalidConcept[5]", concept_provider=get_concept_library()
            )

    def test_empty_string_raises_value_error(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test that an empty string raises InputStuffSpecsFactorySyntaxError."""
        with pytest.raises(InputStuffSpecsFactoryError, match="Invalid input stuff spec string") as exc_info:
            InputStuffSpecsFactory.make_from_string(domain_code="native", stuff_spec_str="", concept_provider=get_concept_library())
        # This error is raised directly without a cause
        assert exc_info.value.__cause__ is None

    def test_malformed_brackets_with_non_digit(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test that brackets with non-digit content are treated as part of concept string."""
        # The regex will match "native.Text[abc]" as concept="native.Text[abc]", multiplicity=None
        # This will then fail during concept validation with ConceptCodeError
        with pytest.raises(InputStuffSpecsFactoryError) as exc_info:
            InputStuffSpecsFactory.make_from_string(domain_code="native", stuff_spec_str="native.Text[abc]", concept_provider=get_concept_library())
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ConceptStringError)

    def test_multiplicity_zero_in_brackets(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test parsing a concept string with 0 in brackets."""
        result = InputStuffSpecsFactory.make_from_string(
            domain_code="native", stuff_spec_str="native.Text[0]", concept_provider=get_concept_library()
        )

        assert isinstance(result, StuffSpec)
        assert result.concept.concept_ref == "native.Text"
        assert result.multiplicity == 0

    def test_return_type(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test that the method returns an StuffSpec instance."""
        result = InputStuffSpecsFactory.make_from_string(domain_code="native", stuff_spec_str="native.Text", concept_provider=get_concept_library())
        assert isinstance(result, StuffSpec)

    def test_concept_attribute_access(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test that the returned StuffSpec has proper concept attributes."""
        result = InputStuffSpecsFactory.make_from_string(
            domain_code="native", stuff_spec_str="native.Text[5]", concept_provider=get_concept_library()
        )

        assert hasattr(result, "concept")
        assert hasattr(result, "multiplicity")
        assert result.concept.concept_ref == "native.Text"
        assert result.concept.code == "Text"

    def test_edge_case_very_long_number(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test parsing with a very long number in brackets."""
        result = InputStuffSpecsFactory.make_from_string(
            domain_code="native", stuff_spec_str="native.Text[999999]", concept_provider=get_concept_library()
        )

        assert result.multiplicity == 999999
        assert result.concept.concept_ref == "native.Text"

    def test_whitespace_not_trimmed(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test that whitespace is not automatically trimmed."""
        # Whitespace should cause domain validation to fail
        with pytest.raises(InputStuffSpecsFactoryError) as exc_info:
            InputStuffSpecsFactory.make_from_string(domain_code="native", stuff_spec_str=" native.Text", concept_provider=get_concept_library())
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ConceptStringError)

        # Trailing whitespace should cause concept code validation to fail
        with pytest.raises(InputStuffSpecsFactoryError) as exc_info:
            InputStuffSpecsFactory.make_from_string(domain_code="native", stuff_spec_str="native.Text ", concept_provider=get_concept_library())
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ConceptStringError)

    def test_multiple_brackets_treated_as_concept_name(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test that multiple brackets are treated as part of the concept name."""
        # "native.Text[5][10]" should match as concept="native.Text[5]", multiplicity=10
        # This will fail during concept code validation
        with pytest.raises(InputStuffSpecsFactoryError) as exc_info:
            InputStuffSpecsFactory.make_from_string(domain_code="native", stuff_spec_str="native.Text[5][10]", concept_provider=get_concept_library())
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ConceptStringError)

    def test_brackets_at_start_treated_as_concept_name(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test that brackets at the start are part of the concept name."""
        # This will fail during domain validation
        with pytest.raises(InputStuffSpecsFactoryError) as exc_info:
            InputStuffSpecsFactory.make_from_string(domain_code="native", stuff_spec_str="[5]native.Text", concept_provider=get_concept_library())
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ConceptStringError)

    @pytest.mark.parametrize(
        ("domain_code", "stuff_spec_str", "expected_concept_ref", "expected_multiplicity", "description"),
        CONCEPT_CODE_RESOLUTION_TEST_CASES,
    )
    def test_concept_code_resolution(
        self,
        domain_code: str,
        stuff_spec_str: str,
        expected_concept_ref: str,
        expected_multiplicity: int | bool | None,
        description: str,
        load_empty_library: Callable[[], None],
    ):
        """Test that concept codes are resolved correctly with domain and concept_codes_from_same_domain.

        This tests:
        1. Native concepts are always recognized regardless of domain parameter
        2. concept_codes_from_same_domain helps resolve ambiguous concept codes
        """
        load_empty_library()
        result = InputStuffSpecsFactory.make_from_string(
            domain_code=domain_code, stuff_spec_str=stuff_spec_str, concept_provider=get_concept_library()
        )

        assert isinstance(result, StuffSpec)
        assert result.concept.concept_ref == expected_concept_ref, f"Failed: {description}"
        assert result.multiplicity == expected_multiplicity, f"Failed: {description}"

    @pytest.mark.parametrize(
        ("domain_code", "stuff_spec_str", "expected_concept_ref", "expected_multiplicity"),
        EXPLICIT_DOMAIN_IN_STRING_TEST_CASES,
    )
    def test_explicit_domain_in_string(
        self,
        domain_code: str,
        stuff_spec_str: str,
        expected_concept_ref: str,
        expected_multiplicity: int | bool | None,
        load_empty_library: Callable[[], None],
    ):
        """Test that explicitly specifying a domain in the requirement string works correctly."""
        load_empty_library()
        result = InputStuffSpecsFactory.make_from_string(
            domain_code=domain_code, stuff_spec_str=stuff_spec_str, concept_provider=get_concept_library()
        )

        assert isinstance(result, StuffSpec)
        assert result.concept.concept_ref == expected_concept_ref
        assert result.multiplicity == expected_multiplicity
