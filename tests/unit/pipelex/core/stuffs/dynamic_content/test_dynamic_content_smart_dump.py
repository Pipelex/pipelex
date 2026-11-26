from tests.unit.pipelex.core.stuffs.dynamic_content.cases import DynamicContentCases, SampleDynamicContent


class TestDynamicContentSmartDump:
    """Tests for DynamicContent.smart_dump() method."""

    def test_smart_dump_returns_dict(self):
        """Verify smart_dump returns a dict with all fields."""
        content = SampleDynamicContent(name=DynamicContentCases.SAMPLE_NAME, value=DynamicContentCases.SAMPLE_VALUE)
        result = content.smart_dump()
        assert result == DynamicContentCases.EXPECTED_SMART_DUMP
        assert isinstance(result, dict)

    def test_smart_dump_different_values(self):
        """Verify smart_dump handles different values correctly."""
        content = SampleDynamicContent(name="Different", value=999)
        result = content.smart_dump()
        assert result == {"name": "Different", "value": 999}
        assert isinstance(result, dict)
