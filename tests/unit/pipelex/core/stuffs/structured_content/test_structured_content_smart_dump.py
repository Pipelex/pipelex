from tests.unit.pipelex.core.stuffs.structured_content.test_data import SampleStructuredContent, TestData


class TestStructuredContentSmartDump:
    """Tests for StructuredContent.smart_dump() method."""

    def test_smart_dump_returns_dict_minimal(self):
        """Verify smart_dump returns a dict with all fields (including None for optionals)."""
        content = SampleStructuredContent(name=TestData.SAMPLE_NAME, value=TestData.SAMPLE_VALUE)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_MINIMAL
        assert isinstance(result, dict)

    def test_smart_dump_returns_dict_full(self):
        """Verify smart_dump returns a dict with all populated fields."""
        content = SampleStructuredContent(
            name=TestData.SAMPLE_NAME,
            value=TestData.SAMPLE_VALUE,
            description=TestData.SAMPLE_DESCRIPTION,
        )
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_FULL
        assert isinstance(result, dict)
