from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity

# Test cases format: (nb_output, multiple_output, expected_result, test_description)
MAKE_VARIABLE_MULTIPLICITY_TEST_CASES: list[tuple[int | None, bool | None, VariableMultiplicity | None, str]] = [
    # nb_output, multiple_output, expected_result, description
    # Test cases where nb_output takes precedence
    (3, None, 3, "nb_output=3, multiple_output=None -> returns 3"),
    (5, False, 5, "nb_output=5, multiple_output=False -> returns 5 (nb_output takes precedence)"),
    (1, True, 1, "nb_output=1, multiple_output=True -> returns 1 (nb_output takes precedence)"),
    (10, None, 10, "nb_output=10, multiple_output=None -> returns 10"),
    # Test cases where multiple_output=True is used
    (None, True, True, "nb_output=None, multiple_output=True -> returns True"),
    (0, True, True, "nb_output=0 (falsy), multiple_output=True -> returns True"),
    # Test cases where default (None) is returned
    (None, None, None, "nb_output=None, multiple_output=None -> returns None (default)"),
    (None, False, None, "nb_output=None, multiple_output=False -> returns None"),
    (0, None, None, "nb_output=0 (falsy), multiple_output=None -> returns None"),
    (0, False, None, "nb_output=0 (falsy), multiple_output=False -> returns None"),
    # Edge cases with negative numbers (should still be truthy)
    (-1, None, -1, "nb_output=-1 (truthy), multiple_output=None -> returns -1"),
    (-5, True, -5, "nb_output=-5 (truthy), multiple_output=True -> returns -5 (nb_output takes precedence)"),
    # Edge cases with large numbers
    (1000, None, 1000, "nb_output=1000, multiple_output=None -> returns 1000"),
    (999999, False, 999999, "nb_output=999999, multiple_output=False -> returns 999999"),
]
