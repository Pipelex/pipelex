from typing import Any, ClassVar


class TestData:
    # Input content
    SAMPLE_TEXT = "Hello World"
    SAMPLE_TEXT_WITH_MARKDOWN = "# Header\n\nSome **bold** text"
    SAMPLE_TEXT_WITH_HTML_CHARS = "Use <b> for bold & <i> for italic"

    # Expected outputs for smart_dump
    EXPECTED_SMART_DUMP: ClassVar[dict[str, Any]] = {"text": "Hello World"}
    EXPECTED_SMART_DUMP_WITH_MARKDOWN: ClassVar[dict[str, Any]] = {"text": "# Header\n\nSome **bold** text"}

    # Expected outputs for render methods
    EXPECTED_RENDERED_PLAIN = "Hello World"
    EXPECTED_RENDERED_MARKDOWN = "Hello World"
    # rendered_html escapes HTML special characters (pure text, not interpreted as markdown)
    EXPECTED_RENDERED_HTML = "Hello World"
    EXPECTED_RENDERED_JSON = '{"text": "Hello World"}'
    EXPECTED_RENDERED_FOR_PROMPT = "Hello World"

    # Expected outputs for markdown content
    EXPECTED_RENDERED_MARKDOWN_WITH_MD = "# Header\n\nSome **bold** text"

    # Expected outputs for text with HTML special characters
    EXPECTED_RENDERED_HTML_WITH_SPECIAL_CHARS = "Use &lt;b&gt; for bold &amp; &lt;i&gt; for italic"
