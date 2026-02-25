from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.urls import URLs
from tests.unit.pipelex.core.stuffs.text_and_images_content.test_data import TestData


class TestTextAndImagesContentSmartDump:
    """Tests for TextAndImagesContent.smart_dump() method."""

    def test_smart_dump_returns_dict_text_only(self):
        """Verify smart_dump returns a dict with text and images keys."""
        content = TextAndImagesContent(text=TestData.SAMPLE_TEXT, images=None)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_TEXT_ONLY
        assert isinstance(result, dict)

    def test_smart_dump_returns_dict_full(self):
        """Verify smart_dump returns a dict with nested content."""
        # Create fresh instances to avoid test data mutation issues
        text = TextContent(text="Hello World")
        images = [
            ImageContent(url=URLs.png_example_1),
            ImageContent(url=URLs.png_example_2),
        ]
        content = TextAndImagesContent(text=text, images=images)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_FULL
        assert isinstance(result, dict)

    def test_smart_dump_empty_content(self):
        """Verify smart_dump handles empty content."""
        content = TextAndImagesContent(text=None, images=None)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_EMPTY
        assert isinstance(result, dict)
