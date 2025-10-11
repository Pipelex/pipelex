import pytest

from pipelex.core.pipes.pipe_run_params import (
    OutputMultiplicityResolution,
    PipeOutputMultiplicity,
    make_output_multiplicity,
    output_multiplicity_to_apply,
)
from tests.unit.pipelex.core.pipes.data import MAKE_OUTPUT_MULTIPLICITY_TEST_CASES, OUTPUT_MULTIPLICITY_TO_APPLY_TEST_CASES


class TestMakeOutputMultiplicity:
    @pytest.mark.parametrize(
        ("nb_output", "multiple_output", "expected_result", "description"),
        MAKE_OUTPUT_MULTIPLICITY_TEST_CASES,
        ids=[case[3] for case in MAKE_OUTPUT_MULTIPLICITY_TEST_CASES],
    )
    def test_make_output_multiplicity_all_cases(
        self,
        nb_output: int | None,
        multiple_output: bool | None,
        expected_result: PipeOutputMultiplicity | None,
        description: str,
    ):
        """Test make_output_multiplicity with all parameter combinations."""
        result = make_output_multiplicity(nb_output=nb_output, multiple_output=multiple_output)
        assert result == expected_result, f"Failed case: {description}"

    def test_nb_output_precedence_over_multiple_output(self):
        """Test that nb_output takes precedence when both parameters are provided."""
        # When both are provided and nb_output is truthy, it should take precedence
        result = make_output_multiplicity(nb_output=3, multiple_output=True)
        assert result == 3

        result = make_output_multiplicity(nb_output=1, multiple_output=False)
        assert result == 1

        # When nb_output is falsy (0), multiple_output should be used
        result = make_output_multiplicity(nb_output=0, multiple_output=True)
        assert result is True

    def test_return_types(self):
        """Test that the function returns the correct types."""
        # Should return int when nb_output is provided
        result = make_output_multiplicity(nb_output=5, multiple_output=None)
        assert isinstance(result, int)
        assert result == 5

        # Should return bool when multiple_output=True and nb_output is falsy/None
        result = make_output_multiplicity(nb_output=None, multiple_output=True)
        assert isinstance(result, bool)
        assert result is True

        # Should return None when both are falsy/None
        result = make_output_multiplicity(nb_output=None, multiple_output=None)
        assert result is None

        result = make_output_multiplicity(nb_output=0, multiple_output=False)
        assert result is None

    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Negative numbers should still be truthy
        result = make_output_multiplicity(nb_output=-1, multiple_output=True)
        assert result == -1

        # Large numbers
        result = make_output_multiplicity(nb_output=999999, multiple_output=None)
        assert result == 999999

        # Zero is falsy, so multiple_output should be used
        result = make_output_multiplicity(nb_output=0, multiple_output=True)
        assert result is True

        # Both falsy should return None
        result = make_output_multiplicity(nb_output=0, multiple_output=False)
        assert result is None

    def test_mutually_exclusive_logic(self):
        """Test the mutually exclusive behavior of the parameters."""
        # nb_output takes precedence when truthy
        assert make_output_multiplicity(nb_output=2, multiple_output=True) == 2
        assert make_output_multiplicity(nb_output=2, multiple_output=False) == 2

        # multiple_output is used when nb_output is falsy
        assert make_output_multiplicity(nb_output=0, multiple_output=True) is True
        assert make_output_multiplicity(nb_output=None, multiple_output=True) is True

        # Default case when both are falsy/None
        assert make_output_multiplicity(nb_output=0, multiple_output=False) is None
        assert make_output_multiplicity(nb_output=None, multiple_output=False) is None
        assert make_output_multiplicity(nb_output=None, multiple_output=None) is None

    def test_function_signature_and_return_annotation(self):
        """Test that the function can be called with the expected signature."""
        # Test with keyword arguments
        result = make_output_multiplicity(nb_output=3, multiple_output=None)
        assert result == 3

        # Test with positional arguments
        result = make_output_multiplicity(5, False)
        assert result == 5

        # Test with mixed arguments
        result = make_output_multiplicity(nb_output=2, multiple_output=True)
        assert result == 2


class TestOutputMultiplicityToApply:
    """Test cases for output_multiplicity_to_apply function."""

    @pytest.mark.parametrize(
        ("base", "override", "expected_result", "description"),
        OUTPUT_MULTIPLICITY_TO_APPLY_TEST_CASES,
        ids=[case[3] for case in OUTPUT_MULTIPLICITY_TO_APPLY_TEST_CASES],
    )
    def test_output_multiplicity_to_apply_all_cases(
        self,
        base: PipeOutputMultiplicity | None,
        override: PipeOutputMultiplicity | None,
        expected_result: OutputMultiplicityResolution,
        description: str,
    ):
        """Test output_multiplicity_to_apply with all parameter combinations."""
        result = output_multiplicity_to_apply(base, override)
        assert result.resolved_multiplicity == expected_result.resolved_multiplicity, f"Failed resolved_multiplicity for case: {description}"
        assert result.is_multiple_outputs_enabled == expected_result.is_multiple_outputs_enabled, (
            f"Failed enable_multiple_outputs for case: {description}"
        )
        assert result.specific_output_count == expected_result.specific_output_count, f"Failed specific_output_count for case: {description}"

    def test_override_none_uses_base(self):
        """Test that when override is None, base value is used as-is."""
        # Base None -> single output
        result = output_multiplicity_to_apply(None, None)
        assert result.resolved_multiplicity is None
        assert result.is_multiple_outputs_enabled is False
        assert result.specific_output_count is None

        # Base True -> multiple output, LLM decides
        result = output_multiplicity_to_apply(base_multiplicity=True, override_multiplicity=None)
        assert result.resolved_multiplicity is True
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count is None

        # Base int -> multiple output with specific count
        result = output_multiplicity_to_apply(base_multiplicity=3, override_multiplicity=None)
        assert result.resolved_multiplicity == 3
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count == 3

        # Base False -> single output
        result = output_multiplicity_to_apply(base_multiplicity=False, override_multiplicity=None)
        assert result.resolved_multiplicity is False
        assert result.is_multiple_outputs_enabled is False
        assert result.specific_output_count is None

    def test_override_false_forces_single_output(self):
        """Test that override=False forces single output regardless of base."""
        # Should force single output for any base value
        test_bases = [None, True, False, 1, 5, 10, -1]

        for base in test_bases:
            result = output_multiplicity_to_apply(base_multiplicity=base, override_multiplicity=False)
            assert result.resolved_multiplicity is False, f"Failed for base={base}: resolved_multiplicity should be False"
            assert result.is_multiple_outputs_enabled is False, f"Failed for base={base}: enable_multiple_outputs should be False"
            assert result.specific_output_count is None, f"Failed for base={base}: specific_output_count should be None"

    def test_override_true_enables_multiple_outputs(self):
        """Test that override=True enables multiple outputs, preserving int base values."""
        # Base None -> preserve None but enable multiple
        result = output_multiplicity_to_apply(base_multiplicity=None, override_multiplicity=True)
        assert result.resolved_multiplicity is None
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count is None

        # Base False -> enable multiple, LLM decides count
        result = output_multiplicity_to_apply(base_multiplicity=False, override_multiplicity=True)
        assert result.resolved_multiplicity is True
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count is None

        # Base True -> keep True
        result = output_multiplicity_to_apply(base_multiplicity=True, override_multiplicity=True)
        assert result.resolved_multiplicity is True
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count is None

        # Base int -> preserve count, enable multiple
        for base_int in [1, 3, 5, 10]:
            result = output_multiplicity_to_apply(base_multiplicity=base_int, override_multiplicity=True)
            assert result.resolved_multiplicity == base_int
            assert result.is_multiple_outputs_enabled is True
            assert result.specific_output_count == base_int

    def test_override_int_uses_override_count(self):
        """Test that override int uses the override count and enables multiple outputs."""
        test_bases = [None, True, False, 2, 7]
        override_int = 5

        for base in test_bases:
            result = output_multiplicity_to_apply(base_multiplicity=base, override_multiplicity=override_int)
            assert result.resolved_multiplicity == override_int, f"Failed for base={base}: resolved_multiplicity should be {override_int}"
            assert result.is_multiple_outputs_enabled is True, f"Failed for base={base}: enable_multiple_outputs should be True"
            assert result.specific_output_count == override_int, f"Failed for base={base}: specific_output_count should be {override_int}"

    def test_return_basemodel_structure(self):
        """Test that the function always returns an OutputMultiplicityResolution with correct types."""
        result = output_multiplicity_to_apply(base_multiplicity=None, override_multiplicity=None)
        assert isinstance(result, OutputMultiplicityResolution)

        # Test field types
        assert result.resolved_multiplicity is None or isinstance(result.resolved_multiplicity, (bool, int))
        assert isinstance(result.is_multiple_outputs_enabled, bool)
        assert result.specific_output_count is None or isinstance(result.specific_output_count, int)

    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Negative numbers
        result = output_multiplicity_to_apply(base_multiplicity=-1, override_multiplicity=None)
        assert result.resolved_multiplicity == -1
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count == -1

        result = output_multiplicity_to_apply(base_multiplicity=3, override_multiplicity=-2)
        assert result.resolved_multiplicity == -2
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count == -2

        # Zero values
        result = output_multiplicity_to_apply(base_multiplicity=0, override_multiplicity=None)
        assert result.resolved_multiplicity == 0
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count == 0

        result = output_multiplicity_to_apply(base_multiplicity=True, override_multiplicity=0)
        assert result.resolved_multiplicity == 0
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count == 0

        # Large numbers
        result = output_multiplicity_to_apply(base_multiplicity=1000, override_multiplicity=None)
        assert result.resolved_multiplicity == 1000
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count == 1000

    def test_override_precedence_logic(self):
        """Test the precedence logic where override always takes precedence when provided."""
        # Override False beats any base
        result = output_multiplicity_to_apply(base_multiplicity=True, override_multiplicity=False)
        assert result.resolved_multiplicity is False
        assert result.is_multiple_outputs_enabled is False
        assert result.specific_output_count is None

        result = output_multiplicity_to_apply(base_multiplicity=5, override_multiplicity=False)
        assert result.resolved_multiplicity is False
        assert result.is_multiple_outputs_enabled is False
        assert result.specific_output_count is None

        # Override int beats any base
        result = output_multiplicity_to_apply(base_multiplicity=True, override_multiplicity=3)
        assert result.resolved_multiplicity == 3
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count == 3

        result = output_multiplicity_to_apply(base_multiplicity=7, override_multiplicity=3)
        assert result.resolved_multiplicity == 3
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count == 3

        # Override True with int base preserves int
        result = output_multiplicity_to_apply(base_multiplicity=5, override_multiplicity=True)
        assert result.resolved_multiplicity == 5
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count == 5

        # Override True with bool base becomes True
        result = output_multiplicity_to_apply(base_multiplicity=True, override_multiplicity=True)
        assert result.resolved_multiplicity is True
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count is None

        result = output_multiplicity_to_apply(base_multiplicity=False, override_multiplicity=True)
        assert result.resolved_multiplicity is True
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count is None

    def test_complex_scenarios(self):
        """Test complex real-world scenarios."""
        # Scenario: Pipe has base multiplicity=3, runtime wants to disable it
        result = output_multiplicity_to_apply(base_multiplicity=3, override_multiplicity=False)
        assert result.resolved_multiplicity is False
        assert result.is_multiple_outputs_enabled is False
        assert result.specific_output_count is None

        # Scenario: Pipe has no base multiplicity, runtime wants 5 outputs
        result = output_multiplicity_to_apply(base_multiplicity=None, override_multiplicity=5)
        assert result.resolved_multiplicity == 5
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count == 5

        # Scenario: Pipe has base True, runtime wants specific count
        result = output_multiplicity_to_apply(base_multiplicity=True, override_multiplicity=2)
        assert result.resolved_multiplicity == 2
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count == 2

        # Scenario: Pipe has base count, runtime wants to enable but let LLM decide
        result = output_multiplicity_to_apply(base_multiplicity=4, override_multiplicity=True)
        assert result.resolved_multiplicity == 4  # Preserves base count
        assert result.is_multiple_outputs_enabled is True
        assert result.specific_output_count == 4
