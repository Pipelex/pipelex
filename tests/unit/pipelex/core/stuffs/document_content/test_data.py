from typing import Any, ClassVar

from pipelex.urls import URLs


class TestData:
    # Input content
    SAMPLE_URL = URLs.pdf_example_1
    SAMPLE_PUBLIC_URL = "Report.pdf"
    SAMPLE_MIME_TYPE = "application/pdf"

    # Expected outputs for smart_dump (minimal)
    EXPECTED_SMART_DUMP_MINIMAL: ClassVar[dict[str, Any]] = {
        "url": URLs.pdf_example_1,
        "mime_type": None,
        "public_url": None,
        "filename": None,
    }

    # Expected outputs for smart_dump (with optional fields)
    EXPECTED_SMART_DUMP_FULL: ClassVar[dict[str, Any]] = {
        "url": URLs.pdf_example_1,
        "mime_type": "application/pdf",
        "public_url": "Report.pdf",
        "filename": None,
    }

    # Expected outputs for render methods
    EXPECTED_RENDERED_PLAIN = URLs.pdf_example_1
    EXPECTED_RENDERED_MARKDOWN = f"[{URLs.pdf_example_1}]({URLs.pdf_example_1})"
    EXPECTED_RENDERED_MARKDOWN_WITH_DISPLAY_LINK = f"[Report.pdf]({URLs.pdf_example_1})"
    EXPECTED_RENDERED_HTML = f'<a href="{URLs.pdf_example_1}" class="msg-document">{URLs.pdf_example_1}</a>'
    EXPECTED_RENDERED_HTML_WITH_PUBLIC_URL = '<a href="Report.pdf" class="msg-document">Report.pdf</a>'
    # rendered_for_prompt returns just the URL for documents
    EXPECTED_RENDERED_FOR_PROMPT = URLs.pdf_example_1
