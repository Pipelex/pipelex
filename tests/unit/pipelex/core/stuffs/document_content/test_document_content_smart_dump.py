from pipelex.core.stuffs.document_content import DocumentContent
from tests.unit.pipelex.core.stuffs.document_content.test_data import TestData


class TestDocumentContentSmartDump:
    """Tests for DocumentContent.smart_dump() method."""

    def test_smart_dump_returns_dict_minimal(self):
        """Verify smart_dump returns a dict with all fields (including None for optionals)."""
        content = DocumentContent(url=TestData.SAMPLE_URL)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_MINIMAL
        assert isinstance(result, dict)

    def test_smart_dump_returns_dict_full(self):
        """Verify smart_dump returns a dict with all populated fields."""
        content = DocumentContent(
            url=TestData.SAMPLE_URL,
            public_url=TestData.SAMPLE_PUBLIC_URL,
            mime_type=TestData.SAMPLE_MIME_TYPE,
        )
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_FULL
        assert isinstance(result, dict)
