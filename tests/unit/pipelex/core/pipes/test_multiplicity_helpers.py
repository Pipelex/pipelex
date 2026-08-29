"""Unit tests for the multiplicity projection helpers.

These helpers are the normalization every consumer of `VariableMultiplicity | None` shares:
list-or-not, the exact count when (and only when) the multiplicity is a fixed count above one,
and the collapse of a count of one onto the single form the language says it already is. The
bool/int cases matter because `True == 1` in Python — a variable-length `[]` must never collapse
the way a `[1]` does.
"""

import pytest

from pipelex.core.pipes.variable_multiplicity import (
    VariableMultiplicity,
    fixed_item_count,
    is_multiple_multiplicity,
    normalize_variable_multiplicity,
)


class TestMultiplicityHelpers:
    @pytest.mark.parametrize(
        ("multiplicity", "expected"),
        [
            (None, False),
            (False, False),
            (True, True),
            (1, False),
            (2, True),
            (10, True),
        ],
    )
    def test_is_multiple(self, multiplicity: VariableMultiplicity | None, expected: bool):
        assert is_multiple_multiplicity(multiplicity=multiplicity) is expected

    @pytest.mark.parametrize(
        ("multiplicity", "expected"),
        [
            (None, None),
            (False, None),
            (True, None),
            (1, None),
            (2, 2),
            (10, 10),
        ],
    )
    def test_fixed_item_count(self, multiplicity: VariableMultiplicity | None, expected: int | None):
        assert fixed_item_count(multiplicity=multiplicity) == expected

    @pytest.mark.parametrize(
        ("multiplicity", "expected"),
        [
            (None, None),
            (True, True),
            (False, False),
            (1, None),
            (2, 2),
            (10, 10),
        ],
    )
    def test_normalize(self, multiplicity: VariableMultiplicity | None, expected: VariableMultiplicity | None):
        """The `[1]`-is-single ruling, applied wherever a multiplicity is built.

        Every site that turns authored syntax or caller arguments into a `VariableMultiplicity` routes
        through this, so the value `1` never reaches a consumer and none of them has to remember why.
        """
        assert normalize_variable_multiplicity(multiplicity=multiplicity) == expected

    def test_normalize_leaves_a_variable_list_alone(self):
        """`bool` is a subclass of `int` and `True == 1`, so `[]` must not collapse the way `[1]` does."""
        assert normalize_variable_multiplicity(multiplicity=True) is True

    def test_normalize_does_not_silently_repair_an_invalid_count(self):
        """`[0]` is invalid syntax the parser refuses; collapsing it here would hide that."""
        assert normalize_variable_multiplicity(multiplicity=0) == 0
