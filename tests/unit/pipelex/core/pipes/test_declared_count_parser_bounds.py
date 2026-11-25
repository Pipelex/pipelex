import pytest
from pydantic import ValidationError

from pipelex.core.pipes.declared_count_bounds import DECLARED_ITEM_COUNT_CEILING, DECLARED_ITEM_COUNT_MAX_DIGITS
from pipelex.core.pipes.exceptions import PipeVariableMultiplicityError
from pipelex.core.pipes.variable_multiplicity import fixed_count_from_digits, multiplicity_from_bracket_content, parse_concept_with_multiplicity
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class TestDeclaredCountParserBounds:
    def test_the_ceiling_is_the_largest_count_the_digit_bound_writes(self) -> None:
        assert DECLARED_ITEM_COUNT_MAX_DIGITS == 9
        assert DECLARED_ITEM_COUNT_CEILING == 999_999_999

    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            ("Text[999999999]", 999_999_999),
            ("Text[0001000]", 1000),
            ("domain.Concept[00000000000042]", 42),
        ],
    )
    def test_a_count_of_nine_digits_or_fewer_parses(self, spec: str, expected: int) -> None:
        """Leading zeros are not counted, so a padded count parses to its value."""
        assert parse_concept_with_multiplicity(spec).multiplicity == expected

    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            pytest.param(f"Text[{'0' * 5000}7]", 7, id="past-python-int-string-limit"),
            pytest.param(f"domain.Concept[{'0' * 4301}999999999]", 999_999_999, id="nine-significant-digits"),
        ],
    )
    def test_leading_zeros_past_pythons_conversion_limit_parse_to_their_value(self, spec: str, expected: int) -> None:
        """Thousands of leading zeros are not significant digits: they parse, never reaching Python's 4,300-digit guard."""
        assert parse_concept_with_multiplicity(spec).multiplicity == expected
        assert fixed_count_from_digits(digits=f"{'0' * 5000}7", slot="the input 'items'") == 7

    @pytest.mark.parametrize("spec", ["Text[1000000000]", f"Text[{'9' * 5000}]", "domain.Concept[1234567890]?"])
    def test_a_count_of_more_digits_is_refused_before_it_is_converted(self, spec: str) -> None:
        """A count of thousands of digits is our typed refusal, never Python's guard on long integer strings."""
        with pytest.raises(PipeVariableMultiplicityError, match="more than any runtime allows"):
            parse_concept_with_multiplicity(spec)

    def test_the_bracket_suffix_reader_holds_the_same_bound(self) -> None:
        assert multiplicity_from_bracket_content(bracket_content="999999999") == 999_999_999
        with pytest.raises(PipeVariableMultiplicityError, match="written with 10 digits"):
            multiplicity_from_bracket_content(bracket_content="1000000000")

    def test_the_refusal_names_the_slot(self) -> None:
        with pytest.raises(PipeVariableMultiplicityError, match="the input 'items'"):
            fixed_count_from_digits(digits="12345678901", slot="the input 'items'")

    def test_a_step_nb_output_past_the_ceiling_is_refused(self) -> None:
        assert SubPipeBlueprint(pipe="make_ideas", nb_output=DECLARED_ITEM_COUNT_CEILING).nb_output == DECLARED_ITEM_COUNT_CEILING
        with pytest.raises(ValidationError, match="make_ideas"):
            SubPipeBlueprint(pipe="make_ideas", nb_output=DECLARED_ITEM_COUNT_CEILING + 1)
