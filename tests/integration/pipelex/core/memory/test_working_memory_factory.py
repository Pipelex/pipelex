from typing import TYPE_CHECKING

from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_content import ImageContent, PageContent, TextAndImagesContent, TextContent

if TYPE_CHECKING:
    from pipelex.client.protocol import CompactMemory


class TestWorkingMemoryFactory:
    def test_make_from_compact_memory_with_text_content(self):
        compact_memory: CompactMemory = {
            "text_item": {
                "concept_code": NativeConceptEnum.TEXT,
                "content": "Hello, world!",
            },
        }

        working_memory = WorkingMemoryFactory.make_from_compact_memory(compact_memory)

        assert working_memory is not None
        assert "text_item" in working_memory.root

        stuff = working_memory.root["text_item"]
        assert stuff.concept.code == NativeConceptEnum.TEXT
        assert isinstance(stuff.content, TextContent)
        assert stuff.content.text == "Hello, world!"

    def test_make_from_compact_memory_with_complex_nested_content(self):
        """Test deserialization of compact memory with complex nested structured content."""
        compact_memory: CompactMemory = {
            "complex_page": {
                "concept_code": NativeConceptEnum.PAGE,
                "content": {
                    "text_and_images": {
                        "text": {
                            "text": "This is a complex document page with multiple images and rich text content. "
                            "It demonstrates nested structured content handling.",
                        },
                        "images": [
                            {
                                "url": "mock_url",
                                "caption": "First image showing data visualization",
                                "source_prompt": "Generate a chart showing quarterly sales data",
                            },
                            {
                                "url": ("data:image/png;base64,mock_base64"),
                                "caption": "Second image with base64 data",
                                "base_64": ("mock_base64"),
                            },
                            {"url": "/local/path/diagram.png", "caption": "System architecture diagram"},
                        ],
                    },
                    "page_view": {"url": "mock_url", "caption": "Full page screenshot"},
                },
            },
        }

        working_memory = WorkingMemoryFactory.make_from_compact_memory(compact_memory)

        assert working_memory is not None
        assert "complex_page" in working_memory.root

        stuff = working_memory.root["complex_page"]
        assert stuff.concept.code == NativeConceptEnum.PAGE
        assert isinstance(stuff.content, PageContent)

        # Verify text_and_images structure
        page_content = stuff.content
        assert isinstance(page_content.text_and_images, TextAndImagesContent)

        # Verify text content
        text_content = page_content.text_and_images.text
        assert text_content is not None
        assert isinstance(text_content, TextContent)
        assert "complex document page" in text_content.text

        # Verify images
        images = page_content.text_and_images.images
        assert images is not None
        assert len(images) == 3

        # Check first image
        first_image = images[0]
        assert isinstance(first_image, ImageContent)
        assert first_image.url == "mock_url"
        assert first_image.caption == "First image showing data visualization"
        assert first_image.source_prompt == "Generate a chart showing quarterly sales data"

        # Check second image (with base64)
        second_image = images[1]
        assert isinstance(second_image, ImageContent)
        expected_base64 = "mock_base64"
        assert second_image.base_64 == expected_base64
        assert second_image.caption == "Second image with base64 data"

        # Check third image
        third_image = images[2]
        assert isinstance(third_image, ImageContent)
        assert third_image.url == "/local/path/diagram.png"
        assert third_image.caption == "System architecture diagram"

        # Verify page_view
        page_view = page_content.page_view
        assert page_view is not None
        assert isinstance(page_view, ImageContent)
        assert page_view.url == "mock_url"
        assert page_view.caption == "Full page screenshot"

    def test_make_from_compact_memory_empty(self):
        """Test deserialization of empty compact memory."""
        compact_memory: CompactMemory = {}

        working_memory = WorkingMemoryFactory.make_from_compact_memory(compact_memory)

        assert working_memory is not None
        assert len(working_memory.root) == 0

    def test_make_from_compact_memory_multiple_items(self):
        """Test deserialization of compact memory with multiple items."""
        compact_memory: CompactMemory = {
            "text1": {
                "concept_code": NativeConceptEnum.TEXT,
                "content": "First text",
            },
            "text2": {
                "concept_code": NativeConceptEnum.TEXT,
                "content": "Second text",
            },
        }

        working_memory = WorkingMemoryFactory.make_from_compact_memory(compact_memory)

        assert working_memory is not None
        assert len(working_memory.root) == 2
        assert "text1" in working_memory.root
        assert "text2" in working_memory.root

        # Verify text content
        text1_stuff = working_memory.root["text1"]
        assert isinstance(text1_stuff.content, TextContent)
        assert text1_stuff.content.text == "First text"

        text2_stuff = working_memory.root["text2"]
        assert isinstance(text2_stuff.content, TextContent)
        assert text2_stuff.content.text == "Second text"
