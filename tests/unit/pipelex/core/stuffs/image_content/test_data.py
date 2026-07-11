from typing import Any, ClassVar

from pipelex.urls import URLs


class TestData:
    # Input content
    SAMPLE_URL = URLs.png_example_1
    SAMPLE_PUBLIC_URL = "https://d2cinlfp2qnig1.cloudfront.net/logo/Pipelex-logo-wot-1119x352.png"
    SAMPLE_CAPTION = "A beautiful sunset"
    SAMPLE_MIME_TYPE = "image/png"
    SAMPLE_SOURCE_PROMPT = "sunset over mountains"

    # Expected outputs for smart_dump (minimal)
    EXPECTED_SMART_DUMP_MINIMAL: ClassVar[dict[str, Any]] = {
        "url": URLs.png_example_1,
        "public_url": None,
        "source_prompt": None,
        "source_negative_prompt": None,
        "caption": None,
        "mime_type": None,
        "width": None,
        "height": None,
        "filename": None,
    }

    # Expected outputs for smart_dump (with optional fields)
    EXPECTED_SMART_DUMP_FULL: ClassVar[dict[str, Any]] = {
        "url": URLs.png_example_1,
        "public_url": "https://d2cinlfp2qnig1.cloudfront.net/logo/Pipelex-logo-wot-1119x352.png",
        "source_prompt": "sunset over mountains",
        "source_negative_prompt": None,
        "caption": "A beautiful sunset",
        "mime_type": "image/png",
        "width": None,
        "height": None,
        "filename": None,
    }

    # Expected outputs for render methods
    EXPECTED_RENDERED_PLAIN = URLs.png_example_1
    EXPECTED_RENDERED_MARKDOWN = f"![{URLs.png_example_1}]({URLs.png_example_1})"
    EXPECTED_RENDERED_HTML = f'<img src="{URLs.png_example_1}" class="msg-img">'
    EXPECTED_RENDERED_HTML_WITH_DISPLAY_LINK = '<img src="https://d2cinlfp2qnig1.cloudfront.net/logo/Pipelex-logo-wot-1119x352.png" class="msg-img">'
    EXPECTED_RENDERED_JSON = f"""{{
    "url": "{URLs.png_example_1}",
    "public_url": null,
    "source_prompt": null,
    "source_negative_prompt": null,
    "caption": null,
    "mime_type": null,
    "width": null,
    "height": null,
    "filename": null
}}"""
    EXPECTED_RENDERED_JSON_WITH_PROMPT = f"""{{
    "url": "{URLs.png_example_1}",
    "public_url": null,
    "source_prompt": "sunset over mountains",
    "source_negative_prompt": null,
    "caption": null,
    "mime_type": null,
    "width": null,
    "height": null,
    "filename": null
}}"""
    # rendered_for_prompt returns just the URL for images
    EXPECTED_RENDERED_FOR_PROMPT = URLs.png_example_1
