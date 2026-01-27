from typing import Any, ClassVar


class TestData:
    # Input content
    SAMPLE_TEXT = "Hello World"
    SAMPLE_TEXT_WITH_MARKDOWN = "# Header\n\nSome **bold** text"

    # Expected outputs for smart_dump
    EXPECTED_SMART_DUMP: ClassVar[dict[str, Any]] = {"text": "Hello World"}
    EXPECTED_SMART_DUMP_WITH_MARKDOWN: ClassVar[dict[str, Any]] = {"text": "# Header\n\nSome **bold** text"}

    # Expected outputs for render methods
    EXPECTED_RENDERED_PLAIN = "Hello World"
    EXPECTED_RENDERED_MARKDOWN = "Hello World"
    EXPECTED_RENDERED_HTML = "<p>Hello World</p>"
    EXPECTED_RENDERED_JSON = '{"text": "Hello World"}'
    EXPECTED_RENDERED_FOR_PROMPT = "Hello World"

    # Expected outputs for markdown content
    EXPECTED_RENDERED_MARKDOWN_WITH_MD = "# Header\n\nSome **bold** text"
