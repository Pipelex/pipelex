from typing import Any, ClassVar

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.urls import URLs


class TestData:
    # Input content
    SAMPLE_TEXT = TextContent(text="Hello World")
    SAMPLE_IMAGES: ClassVar[list[ImageContent]] = [
        ImageContent(url=URLs.png_example_1),
        ImageContent(url=URLs.jpg_example_1),
    ]

    # Expected outputs for smart_dump (text only)
    EXPECTED_SMART_DUMP_TEXT_ONLY: ClassVar[dict[str, Any]] = {
        "text": {"text": "Hello World"},
        "images": None,
    }

    # Expected outputs for smart_dump (text and images)
    EXPECTED_SMART_DUMP_FULL: ClassVar[dict[str, Any]] = {
        "text": {"text": "Hello World"},
        "images": [
            {
                "url": URLs.png_example_1,
                "public_url": None,
                "source_prompt": None,
                "source_negative_prompt": None,
                "caption": None,
                "mime_type": None,
                "size": None,
                "filename": None,
            },
            {
                "url": URLs.png_example_2,
                "public_url": None,
                "source_prompt": None,
                "source_negative_prompt": None,
                "caption": None,
                "mime_type": None,
                "size": None,
                "filename": None,
            },
        ],
    }

    # Expected outputs for render methods
    EXPECTED_RENDERED_PLAIN = "Hello World"
    EXPECTED_RENDERED_MARKDOWN = "Hello World"
    EXPECTED_RENDERED_FOR_PROMPT = "Hello World"
    # TextContent.rendered_html escapes HTML chars, no longer wraps in <p> tags
    EXPECTED_RENDERED_HTML = "Hello World"

    # Empty content test cases
    EXPECTED_SMART_DUMP_EMPTY: ClassVar[dict[str, Any]] = {"text": None, "images": None}
    EXPECTED_RENDERED_PLAIN_EMPTY = ""
