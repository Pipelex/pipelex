from pipelex.core.pipes.pipe_run_params import OutputMultiplicityResolution, PipeOutputMultiplicity

# Test cases format: (nb_output, multiple_output, expected_result, test_description)
MAKE_OUTPUT_MULTIPLICITY_TEST_CASES: list[tuple[int | None, bool | None, PipeOutputMultiplicity | None, str]] = [
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


# Test cases format: (base, override, expected_result, description)
OUTPUT_MULTIPLICITY_TO_APPLY_TEST_CASES: list[
    tuple[PipeOutputMultiplicity | None, PipeOutputMultiplicity | None, OutputMultiplicityResolution, str]
] = [
    # base, override, expected_result, description
    # Override is None - use base value as-is
    (
        None,
        None,
        OutputMultiplicityResolution(resolved_multiplicity=None, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=None, override=None",
    ),
    (
        True,
        None,
        OutputMultiplicityResolution(resolved_multiplicity=True, is_multiple_outputs_enabled=True, specific_output_count=None),
        "base=True, override=None",
    ),
    (
        False,
        None,
        OutputMultiplicityResolution(resolved_multiplicity=False, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=False, override=None",
    ),
    (
        3,
        None,
        OutputMultiplicityResolution(resolved_multiplicity=3, is_multiple_outputs_enabled=True, specific_output_count=3),
        "base=3, override=None",
    ),
    (
        5,
        None,
        OutputMultiplicityResolution(resolved_multiplicity=5, is_multiple_outputs_enabled=True, specific_output_count=5),
        "base=5, override=None",
    ),
    # Override is False - force single output regardless of base
    (
        None,
        False,
        OutputMultiplicityResolution(resolved_multiplicity=False, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=None, override=False",
    ),
    (
        True,
        False,
        OutputMultiplicityResolution(resolved_multiplicity=False, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=True, override=False",
    ),
    (
        False,
        False,
        OutputMultiplicityResolution(resolved_multiplicity=False, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=False, override=False",
    ),
    (
        3,
        False,
        OutputMultiplicityResolution(resolved_multiplicity=False, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=3, override=False",
    ),
    (
        10,
        False,
        OutputMultiplicityResolution(resolved_multiplicity=False, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=10, override=False",
    ),
    # Override is True - enable multiple outputs
    (
        None,
        True,
        OutputMultiplicityResolution(resolved_multiplicity=None, is_multiple_outputs_enabled=True, specific_output_count=None),
        "base=None, override=True",
    ),
    (
        True,
        True,
        OutputMultiplicityResolution(resolved_multiplicity=True, is_multiple_outputs_enabled=True, specific_output_count=None),
        "base=True, override=True",
    ),
    (
        False,
        True,
        OutputMultiplicityResolution(resolved_multiplicity=True, is_multiple_outputs_enabled=True, specific_output_count=None),
        "base=False, override=True",
    ),
    (
        3,
        True,
        OutputMultiplicityResolution(resolved_multiplicity=3, is_multiple_outputs_enabled=True, specific_output_count=3),
        "base=3, override=True - preserve base count",
    ),
    (
        7,
        True,
        OutputMultiplicityResolution(resolved_multiplicity=7, is_multiple_outputs_enabled=True, specific_output_count=7),
        "base=7, override=True - preserve base count",
    ),
    # Override is int - use override count, enable multiple outputs
    (
        None,
        2,
        OutputMultiplicityResolution(resolved_multiplicity=2, is_multiple_outputs_enabled=True, specific_output_count=2),
        "base=None, override=2",
    ),
    (
        True,
        4,
        OutputMultiplicityResolution(resolved_multiplicity=4, is_multiple_outputs_enabled=True, specific_output_count=4),
        "base=True, override=4",
    ),
    (
        False,
        6,
        OutputMultiplicityResolution(resolved_multiplicity=6, is_multiple_outputs_enabled=True, specific_output_count=6),
        "base=False, override=6",
    ),
    (
        3,
        8,
        OutputMultiplicityResolution(resolved_multiplicity=8, is_multiple_outputs_enabled=True, specific_output_count=8),
        "base=3, override=8 - override takes precedence",
    ),
    (
        5,
        1,
        OutputMultiplicityResolution(resolved_multiplicity=1, is_multiple_outputs_enabled=True, specific_output_count=1),
        "base=5, override=1 - override takes precedence",
    ),
    # Edge cases with negative numbers
    (
        -1,
        None,
        OutputMultiplicityResolution(resolved_multiplicity=-1, is_multiple_outputs_enabled=True, specific_output_count=-1),
        "base=-1, override=None",
    ),
    (
        3,
        -2,
        OutputMultiplicityResolution(resolved_multiplicity=-2, is_multiple_outputs_enabled=True, specific_output_count=-2),
        "base=3, override=-2",
    ),
    # Edge cases with zero
    (
        0,
        None,
        OutputMultiplicityResolution(resolved_multiplicity=0, is_multiple_outputs_enabled=True, specific_output_count=0),
        "base=0, override=None",
    ),
    (
        True,
        0,
        OutputMultiplicityResolution(resolved_multiplicity=0, is_multiple_outputs_enabled=True, specific_output_count=0),
        "base=True, override=0",
    ),
    # Large numbers
    (
        1000,
        None,
        OutputMultiplicityResolution(resolved_multiplicity=1000, is_multiple_outputs_enabled=True, specific_output_count=1000),
        "base=1000, override=None",
    ),
    (
        100,
        999,
        OutputMultiplicityResolution(resolved_multiplicity=999, is_multiple_outputs_enabled=True, specific_output_count=999),
        "base=100, override=999",
    ),
]
