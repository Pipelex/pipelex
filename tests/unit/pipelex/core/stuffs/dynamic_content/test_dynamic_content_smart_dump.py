from tests.unit.pipelex.core.stuffs.dynamic_content.test_data import SampleDynamicContent, TestData


class TestDynamicContentSmartDump:
    """Tests for DynamicContent.smart_dump() method."""

    def test_smart_dump_returns_dict(self):
        """Verify smart_dump returns a dict with all fields."""
        content = SampleDynamicContent(name=TestData.SAMPLE_NAME, value=TestData.SAMPLE_VALUE)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP
        assert isinstance(result, dict)

    def test_smart_dump_different_values(self):
        """Verify smart_dump handles different values correctly."""
        content = SampleDynamicContent(name="Different", value=999)
        result = content.smart_dump()
        assert result == {"name": "Different", "value": 999}
        assert isinstance(result, dict)
