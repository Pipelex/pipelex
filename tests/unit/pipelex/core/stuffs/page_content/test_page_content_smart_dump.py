from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.urls import URLs
from tests.unit.pipelex.core.stuffs.page_content.test_data import TestData


class TestPageContentSmartDump:
    """Tests for PageContent.smart_dump() method."""

    def test_smart_dump_returns_dict_minimal(self):
        """Verify smart_dump returns a dict with text_and_images and page_view keys."""
        text_and_images = TextAndImagesContent(
            text=TextContent(text="Page content text"),
            images=None,
        )
        content = PageContent(text_and_images=text_and_images, page_view=None)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_MINIMAL
        assert isinstance(result, dict)

    def test_smart_dump_returns_dict_full(self):
        """Verify smart_dump returns a dict with page_view included."""
        text_and_images = TextAndImagesContent(
            text=TextContent(text="Page content text"),
            images=None,
        )
        page_view = ImageContent(url=URLs.png_example_1)
        content = PageContent(text_and_images=text_and_images, page_view=page_view)
        result = content.smart_dump()
        assert result == TestData.EXPECTED_SMART_DUMP_FULL
        assert isinstance(result, dict)
