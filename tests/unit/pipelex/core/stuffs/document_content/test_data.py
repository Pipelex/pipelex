from typing import Any, ClassVar


class TestData:
    # Input content
    SAMPLE_URL = "https://example.com/document.pdf"
    SAMPLE_PUBLIC_URL = "Report.pdf"
    SAMPLE_MIME_TYPE = "application/pdf"

    # Expected outputs for smart_dump (minimal)
    EXPECTED_SMART_DUMP_MINIMAL: ClassVar[dict[str, Any]] = {
        "url": "https://example.com/document.pdf",
        "mime_type": None,
        "public_url": None,
        "filename": None,
    }

    # Expected outputs for smart_dump (with optional fields)
    EXPECTED_SMART_DUMP_FULL: ClassVar[dict[str, Any]] = {
        "url": "https://example.com/document.pdf",
        "mime_type": "application/pdf",
        "public_url": "Report.pdf",
        "filename": None,
    }

    # Expected outputs for render methods
    EXPECTED_RENDERED_PLAIN = "https://example.com/document.pdf"
    EXPECTED_RENDERED_MARKDOWN = "[https://example.com/document.pdf](https://example.com/document.pdf)"
    EXPECTED_RENDERED_MARKDOWN_WITH_DISPLAY_LINK = "[Report.pdf](https://example.com/document.pdf)"
    EXPECTED_RENDERED_HTML = '<a href="https://example.com/document.pdf" class="msg-document">https://example.com/document.pdf</a>'
    EXPECTED_RENDERED_HTML_WITH_DISPLAY_LINK = '<a href="Report.pdf" class="msg-document">Report.pdf</a>'
    # rendered_for_prompt returns just the URL for documents
    EXPECTED_RENDERED_FOR_PROMPT = "https://example.com/document.pdf"
