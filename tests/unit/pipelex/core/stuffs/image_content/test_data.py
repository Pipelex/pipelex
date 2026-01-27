from typing import Any, ClassVar


class TestData:
    # Input content
    SAMPLE_URL = "https://example.com/image.png"
    SAMPLE_DISPLAY_LINK = "https://cdn.example.com/image.png"
    SAMPLE_CAPTION = "A beautiful sunset"
    SAMPLE_MIME_TYPE = "image/png"
    SAMPLE_SOURCE_PROMPT = "sunset over mountains"

    # Expected outputs for smart_dump (minimal)
    EXPECTED_SMART_DUMP_MINIMAL: ClassVar[dict[str, Any]] = {
        "url": "https://example.com/image.png",
        "display_link": None,
        "source_prompt": None,
        "source_negative_prompt": None,
        "caption": None,
        "mime_type": None,
        "size": None,
    }

    # Expected outputs for smart_dump (with optional fields)
    EXPECTED_SMART_DUMP_FULL: ClassVar[dict[str, Any]] = {
        "url": "https://example.com/image.png",
        "display_link": "https://cdn.example.com/image.png",
        "source_prompt": "sunset over mountains",
        "source_negative_prompt": None,
        "caption": "A beautiful sunset",
        "mime_type": "image/png",
        "size": None,
    }

    # Expected outputs for render methods
    EXPECTED_RENDERED_PLAIN = "https://example.com/image.png"
    EXPECTED_RENDERED_MARKDOWN = "![https://example.com/image.png](https://example.com/image.png)"
    EXPECTED_RENDERED_HTML = '<img src="https://example.com/image.png" class="msg-img">'
    EXPECTED_RENDERED_HTML_WITH_DISPLAY_LINK = '<img src="https://cdn.example.com/image.png" class="msg-img">'
    EXPECTED_RENDERED_JSON = '{"image_url": "https://example.com/image.png", "source_prompt": null}'
    EXPECTED_RENDERED_JSON_WITH_PROMPT = '{"image_url": "https://example.com/image.png", "source_prompt": "sunset over mountains"}'
    # rendered_for_prompt returns just the URL for images
    EXPECTED_RENDERED_FOR_PROMPT = "https://example.com/image.png"
