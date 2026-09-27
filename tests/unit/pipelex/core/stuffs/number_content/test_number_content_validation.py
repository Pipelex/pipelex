import pytest
from pydantic import ValidationError

from pipelex.core.stuffs.number_content import NumberContent


class TestNumberContentValidation:
    @pytest.mark.parametrize("number", [0, -3, 4.2, 1e308])
    def test_a_finite_number_is_kept(self, number: float) -> None:
        assert NumberContent(number=number).number == number

    @pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
    def test_a_non_finite_number_is_refused(self, non_finite: float) -> None:
        """NaN and the infinities are not JSON numbers: serialization would turn them into null."""
        with pytest.raises(ValidationError, match="number must be finite"):
            NumberContent(number=non_finite)
