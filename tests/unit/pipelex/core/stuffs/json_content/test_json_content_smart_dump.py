from typing import Any

import pytest

from pipelex.core.stuffs.json_content import JSONContent
from tests.unit.pipelex.core.stuffs.json_content.test_data import TestData


class TestJSONContentSmartDump:
    """Tests for JSONContent.smart_dump() method."""

    def test_smart_dump_returns_dict(self):
        """Verify smart_dump returns a dict with json_obj key."""
        content = JSONContent(json_obj=TestData.SAMPLE_JSON_OBJ)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP
        assert isinstance(result, dict)

    def test_smart_dump_with_nested_json(self):
        """Verify smart_dump handles nested JSON objects."""
        content = JSONContent(json_obj=TestData.SAMPLE_NESTED_JSON_OBJ)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_NESTED
        assert isinstance(result, dict)

    def test_smart_dump_empty_object(self):
        """Verify smart_dump handles empty JSON object."""
        content = JSONContent(json_obj=TestData.EMPTY_JSON_OBJ)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_EMPTY
        assert isinstance(result, dict)

    @pytest.mark.parametrize(
        ("json_obj", "expected_output"),
        [
            ({"key": "value"}, {"json_obj": {"key": "value"}}),
            ({"list": [1, 2, 3]}, {"json_obj": {"list": [1, 2, 3]}}),
            ({"null_value": None}, {"json_obj": {"null_value": None}}),
        ],
    )
    def test_smart_dump_various_inputs(self, json_obj: dict[str, Any], expected_output: dict[str, Any]):
        """Verify smart_dump handles various JSON inputs correctly."""
        content = JSONContent(json_obj=json_obj)
        result = content.smart_dump()
        assert result == expected_output
        assert isinstance(result, dict)
