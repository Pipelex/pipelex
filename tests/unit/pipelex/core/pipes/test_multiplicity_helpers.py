"""Unit tests for the multiplicity projection helpers.

These two helpers are the normalization every consumer of `VariableMultiplicity | None`
shares: list-or-not, and the exact count when (and only when) the multiplicity is a fixed
count above one. The bool/int cases matter because `True == 1` in Python — the helpers must
keep `[]` (True) and `[1]` (1) distinct.
"""

import pytest

from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity, fixed_item_count, is_multiple_multiplicity


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
