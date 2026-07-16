from typing import Any, ClassVar

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.urls import URLs


class TestData:
    # Input content
    SAMPLE_TEXT_AND_IMAGES = TextAndImagesContent(
        text=TextContent(text="Page content text"),
        images=None,
    )
    SAMPLE_PAGE_VIEW = ImageContent(url=URLs.png_example_1)

    # Expected outputs for smart_dump (minimal - without page_view)
    EXPECTED_SMART_DUMP_MINIMAL: ClassVar[dict[str, Any]] = {
        "text_and_images": {
            "text": {"text": "Page content text"},
            "images": None,
            "raw_html": None,
        },
        "page_view": None,
    }

    # Expected outputs for smart_dump (with page_view)
    EXPECTED_SMART_DUMP_FULL: ClassVar[dict[str, Any]] = {
        "text_and_images": {
            "text": {"text": "Page content text"},
            "images": None,
            "raw_html": None,
        },
        "page_view": {
            "url": URLs.png_example_1,
            "public_url": None,
            "source_prompt": None,
            "source_negative_prompt": None,
            "caption": None,
            "mime_type": None,
            "width": None,
            "height": None,
            "filename": None,
        },
    }

    # Expected outputs for render methods
    EXPECTED_RENDERED_MARKDOWN = (
        "# text_and_images\n\n## text: ### text: Page content text\n\n## images: None\n\n## raw_html: None\n\n# page_view: None"
    )
    EXPECTED_RENDERED_FOR_PROMPT = (
        "# text_and_images\n\n## text: ### text: Page content text\n\n## images: None\n\n## raw_html: None\n\n# page_view: None"
    )
    # TextAndImagesContent.rendered_html returns the text content (table format, skips None values)
    EXPECTED_RENDERED_HTML = "<table><tr><th>text_and_images</th><td>Page content text</td></tr></table>"
