from tests.unit.pipelex.core.stuffs.structured_content.cases import SampleStructuredContent, StructuredContentCases


class TestStructuredContentSmartDump:
    """Tests for StructuredContent.smart_dump() method."""

    def test_smart_dump_returns_dict_minimal(self):
        """Verify smart_dump returns a dict with all fields (including None for optionals)."""
        content = SampleStructuredContent(name=StructuredContentCases.SAMPLE_NAME, value=StructuredContentCases.SAMPLE_VALUE)
        result = content.smart_dump()
        assert result == StructuredContentCases.EXPECTED_SMART_DUMP_MINIMAL
        assert isinstance(result, dict)

    def test_smart_dump_returns_dict_full(self):
        """Verify smart_dump returns a dict with all populated fields."""
        content = SampleStructuredContent(
            name=StructuredContentCases.SAMPLE_NAME,
            value=StructuredContentCases.SAMPLE_VALUE,
            description=StructuredContentCases.SAMPLE_DESCRIPTION,
        )
        result = content.smart_dump()
        assert result == StructuredContentCases.EXPECTED_SMART_DUMP_FULL
        assert isinstance(result, dict)
