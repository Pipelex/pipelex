from typing import Any

import pytest

from pipelex.core.stuffs.number_content import NumberContent
from tests.unit.pipelex.core.stuffs.number_content.test_data import TestData


class TestNumberContentSmartDump:
    """Tests for NumberContent.smart_dump() method."""

    def test_smart_dump_returns_dict_for_int(self):
        """Verify smart_dump returns a dict for integer values."""
        content = NumberContent(number=TestData.SAMPLE_INT)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_INT
        assert isinstance(result, dict)

    def test_smart_dump_returns_dict_for_float(self):
        """Verify smart_dump returns a dict for float values."""
        content = NumberContent(number=TestData.SAMPLE_FLOAT)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_FLOAT
        assert isinstance(result, dict)

    @pytest.mark.parametrize(
        ("number_input", "expected_output"),
        [
            (0, {"number": 0}),
            (-1, {"number": -1}),
            (1000000, {"number": 1000000}),
            (0.0, {"number": 0.0}),
            (-3.14, {"number": -3.14}),
            (1e10, {"number": 1e10}),
        ],
    )
    def test_smart_dump_various_inputs(self, number_input: float, expected_output: dict[str, Any]):
        """Verify smart_dump handles various numeric inputs correctly."""
        content = NumberContent(number=number_input)
        result = content.smart_dump()
        assert result == expected_output
        assert isinstance(result, dict)
