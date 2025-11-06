from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity, VariableMultiplicityResolution

# Test cases format: (base, override, expected_result, description)
OUTPUT_MULTIPLICITY_TO_APPLY_TEST_CASES: list[
    tuple[VariableMultiplicity | None, VariableMultiplicity | None, VariableMultiplicityResolution, str]
] = [
    # base, override, expected_result, description
    # Override is None - use base value as-is
    (
        None,
        None,
        VariableMultiplicityResolution(resolved_multiplicity=None, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=None, override=None",
    ),
    (
        True,
        None,
        VariableMultiplicityResolution(resolved_multiplicity=True, is_multiple_outputs_enabled=True, specific_output_count=None),
        "base=True, override=None",
    ),
    (
        False,
        None,
        VariableMultiplicityResolution(resolved_multiplicity=False, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=False, override=None",
    ),
    (
        3,
        None,
        VariableMultiplicityResolution(resolved_multiplicity=3, is_multiple_outputs_enabled=True, specific_output_count=3),
        "base=3, override=None",
    ),
    (
        5,
        None,
        VariableMultiplicityResolution(resolved_multiplicity=5, is_multiple_outputs_enabled=True, specific_output_count=5),
        "base=5, override=None",
    ),
    # Override is False - force single output regardless of base
    (
        None,
        False,
        VariableMultiplicityResolution(resolved_multiplicity=False, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=None, override=False",
    ),
    (
        True,
        False,
        VariableMultiplicityResolution(resolved_multiplicity=False, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=True, override=False",
    ),
    (
        False,
        False,
        VariableMultiplicityResolution(resolved_multiplicity=False, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=False, override=False",
    ),
    (
        3,
        False,
        VariableMultiplicityResolution(resolved_multiplicity=False, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=3, override=False",
    ),
    (
        10,
        False,
        VariableMultiplicityResolution(resolved_multiplicity=False, is_multiple_outputs_enabled=False, specific_output_count=None),
        "base=10, override=False",
    ),
    # Override is True - enable multiple outputs
    (
        None,
        True,
        VariableMultiplicityResolution(resolved_multiplicity=None, is_multiple_outputs_enabled=True, specific_output_count=None),
        "base=None, override=True",
    ),
    (
        True,
        True,
        VariableMultiplicityResolution(resolved_multiplicity=True, is_multiple_outputs_enabled=True, specific_output_count=None),
        "base=True, override=True",
    ),
    (
        False,
        True,
        VariableMultiplicityResolution(resolved_multiplicity=True, is_multiple_outputs_enabled=True, specific_output_count=None),
        "base=False, override=True",
    ),
    (
        3,
        True,
        VariableMultiplicityResolution(resolved_multiplicity=3, is_multiple_outputs_enabled=True, specific_output_count=3),
        "base=3, override=True - preserve base count",
    ),
    (
        7,
        True,
        VariableMultiplicityResolution(resolved_multiplicity=7, is_multiple_outputs_enabled=True, specific_output_count=7),
        "base=7, override=True - preserve base count",
    ),
    # Override is int - use override count, enable multiple outputs
    (
        None,
        2,
        VariableMultiplicityResolution(resolved_multiplicity=2, is_multiple_outputs_enabled=True, specific_output_count=2),
        "base=None, override=2",
    ),
    (
        True,
        4,
        VariableMultiplicityResolution(resolved_multiplicity=4, is_multiple_outputs_enabled=True, specific_output_count=4),
        "base=True, override=4",
    ),
    (
        False,
        6,
        VariableMultiplicityResolution(resolved_multiplicity=6, is_multiple_outputs_enabled=True, specific_output_count=6),
        "base=False, override=6",
    ),
    (
        3,
        8,
        VariableMultiplicityResolution(resolved_multiplicity=8, is_multiple_outputs_enabled=True, specific_output_count=8),
        "base=3, override=8 - override takes precedence",
    ),
    (
        5,
        1,
        VariableMultiplicityResolution(resolved_multiplicity=1, is_multiple_outputs_enabled=True, specific_output_count=1),
        "base=5, override=1 - override takes precedence",
    ),
    # Edge cases with negative numbers
    (
        -1,
        None,
        VariableMultiplicityResolution(resolved_multiplicity=-1, is_multiple_outputs_enabled=True, specific_output_count=-1),
        "base=-1, override=None",
    ),
    (
        3,
        -2,
        VariableMultiplicityResolution(resolved_multiplicity=-2, is_multiple_outputs_enabled=True, specific_output_count=-2),
        "base=3, override=-2",
    ),
    # Edge cases with zero
    (
        0,
        None,
        VariableMultiplicityResolution(resolved_multiplicity=0, is_multiple_outputs_enabled=True, specific_output_count=0),
        "base=0, override=None",
    ),
    (
        True,
        0,
        VariableMultiplicityResolution(resolved_multiplicity=0, is_multiple_outputs_enabled=True, specific_output_count=0),
        "base=True, override=0",
    ),
    # Large numbers
    (
        1000,
        None,
        VariableMultiplicityResolution(resolved_multiplicity=1000, is_multiple_outputs_enabled=True, specific_output_count=1000),
        "base=1000, override=None",
    ),
    (
        100,
        999,
        VariableMultiplicityResolution(resolved_multiplicity=999, is_multiple_outputs_enabled=True, specific_output_count=999),
        "base=100, override=999",
    ),
]
