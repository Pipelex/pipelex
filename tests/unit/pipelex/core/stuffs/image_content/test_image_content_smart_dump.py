from pipelex.core.stuffs.image_content import ImageContent
from tests.unit.pipelex.core.stuffs.image_content.test_data import TestData


class TestImageContentSmartDump:
    """Tests for ImageContent.smart_dump() method."""

    def test_smart_dump_returns_dict_minimal(self):
        """Verify smart_dump returns a dict with all fields (including None for optionals)."""
        content = ImageContent(url=TestData.SAMPLE_URL)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_MINIMAL
        assert isinstance(result, dict)

    def test_smart_dump_returns_dict_full(self):
        """Verify smart_dump returns a dict with all populated fields."""
        content = ImageContent(
            url=TestData.SAMPLE_URL,
            public_url=TestData.SAMPLE_PUBLIC_URL,
            source_prompt=TestData.SAMPLE_SOURCE_PROMPT,
            caption=TestData.SAMPLE_CAPTION,
            mime_type=TestData.SAMPLE_MIME_TYPE,
        )
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_FULL
        assert isinstance(result, dict)
