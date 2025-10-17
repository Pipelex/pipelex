import pytest

from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity, make_variable_multiplicity
from tests.unit.pipelex.core.pipes.data import MAKE_VARIABLE_MULTIPLICITY_TEST_CASES


class TestMakeVariableMultiplicity:
    @pytest.mark.parametrize(
        ("nb_output", "multiple_output", "expected_result", "description"),
        MAKE_VARIABLE_MULTIPLICITY_TEST_CASES,
        ids=[case[3] for case in MAKE_VARIABLE_MULTIPLICITY_TEST_CASES],
    )
    def test_make_output_multiplicity_all_cases(
        self,
        nb_output: int | None,
        multiple_output: bool | None,
        expected_result: VariableMultiplicity | None,
        description: str,
    ):
        """Test make_output_multiplicity with all parameter combinations."""
        result = make_variable_multiplicity(nb_items=nb_output, multiple_items=multiple_output)
        assert result == expected_result, f"Failed case: {description}"

    def test_nb_output_precedence_over_multiple_output(self):
        """Test that nb_output takes precedence when both parameters are provided."""
        # When both are provided and nb_output is truthy, it should take precedence
        result = make_variable_multiplicity(nb_items=3, multiple_items=True)
        assert result == 3

        result = make_variable_multiplicity(nb_items=1, multiple_items=False)
        assert result == 1

        # When nb_output is falsy (0), multiple_output should be used
        result = make_variable_multiplicity(nb_items=0, multiple_items=True)
        assert result is True

    def test_return_types(self):
        """Test that the function returns the correct types."""
        # Should return int when nb_output is provided
        result = make_variable_multiplicity(nb_items=5, multiple_items=None)
        assert isinstance(result, int)
        assert result == 5

        # Should return bool when multiple_output=True and nb_output is falsy/None
        result = make_variable_multiplicity(nb_items=None, multiple_items=True)
        assert isinstance(result, bool)
        assert result is True

        # Should return None when both are falsy/None
        result = make_variable_multiplicity(nb_items=None, multiple_items=None)
        assert result is None

        result = make_variable_multiplicity(nb_items=0, multiple_items=False)
        assert result is None

    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Negative numbers should still be truthy
        result = make_variable_multiplicity(nb_items=-1, multiple_items=True)
        assert result == -1

        # Large numbers
        result = make_variable_multiplicity(nb_items=999999, multiple_items=None)
        assert result == 999999

        # Zero is falsy, so multiple_output should be used
        result = make_variable_multiplicity(nb_items=0, multiple_items=True)
        assert result is True

        # Both falsy should return None
        result = make_variable_multiplicity(nb_items=0, multiple_items=False)
        assert result is None

    def test_mutually_exclusive_logic(self):
        """Test the mutually exclusive behavior of the parameters."""
        # nb_output takes precedence when truthy
        assert make_variable_multiplicity(nb_items=2, multiple_items=True) == 2
        assert make_variable_multiplicity(nb_items=2, multiple_items=False) == 2

        # multiple_output is used when nb_output is falsy
        assert make_variable_multiplicity(nb_items=0, multiple_items=True) is True
        assert make_variable_multiplicity(nb_items=None, multiple_items=True) is True

        # Default case when both are falsy/None
        assert make_variable_multiplicity(nb_items=0, multiple_items=False) is None
        assert make_variable_multiplicity(nb_items=None, multiple_items=False) is None
        assert make_variable_multiplicity(nb_items=None, multiple_items=None) is None

    def test_function_signature_and_return_annotation(self):
        """Test that the function can be called with the expected signature."""
        # Test with keyword arguments
        result = make_variable_multiplicity(nb_items=3, multiple_items=None)
        assert result == 3

        # Test with positional arguments
        result = make_variable_multiplicity(5, False)
        assert result == 5

        # Test with mixed arguments
        result = make_variable_multiplicity(nb_items=2, multiple_items=True)
        assert result == 2
