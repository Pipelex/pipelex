from typing import Any, ClassVar

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent


class TestData:
    # Input content
    SAMPLE_TEXT_AND_IMAGES = TextAndImagesContent(
        text=TextContent(text="Page content text"),
        images=None,
    )
    SAMPLE_PAGE_VIEW = ImageContent(url="https://example.com/page-view.png")

    # Expected outputs for smart_dump (minimal - without page_view)
    EXPECTED_SMART_DUMP_MINIMAL: ClassVar[dict[str, Any]] = {
        "text_and_images": {
            "text": {"text": "Page content text"},
            "images": None,
        },
        "page_view": None,
    }

    # Expected outputs for smart_dump (with page_view)
    EXPECTED_SMART_DUMP_FULL: ClassVar[dict[str, Any]] = {
        "text_and_images": {
            "text": {"text": "Page content text"},
            "images": None,
        },
        "page_view": {
            "url": "https://example.com/page-view.png",
            "display_link": None,
            "source_prompt": None,
            "source_negative_prompt": None,
            "caption": None,
            "mime_type": None,
            "size": None,
        },
    }

    # Expected outputs for render methods
    EXPECTED_RENDERED_MARKDOWN = "# text_and_images\n\n## text: ### text: Page content text\n\n## images: None\n\n# page_view: None"
    EXPECTED_RENDERED_FOR_PROMPT = "# text_and_images\n\n## text: ### text: Page content text\n\n## images: None\n\n# page_view: None"
    # TextAndImagesContent.rendered_html returns the text content
    EXPECTED_RENDERED_HTML = "<dl><dt>text_and_images</dt><dd>Page content text</dd><dt>page_view</dt><dd><em>None</em></dd></dl>"
