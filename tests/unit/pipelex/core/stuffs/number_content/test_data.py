from typing import Any, ClassVar


class TestData:
    # Input content - integer
    SAMPLE_INT = 42

    # Input content - float
    SAMPLE_FLOAT = 3.14159

    # Expected outputs for smart_dump
    EXPECTED_SMART_DUMP_INT: ClassVar[dict[str, Any]] = {"number": 42}
    EXPECTED_SMART_DUMP_FLOAT: ClassVar[dict[str, Any]] = {"number": 3.14159}

    # Expected outputs for render methods - integer
    EXPECTED_RENDERED_PLAIN_INT = "42"
    EXPECTED_RENDERED_MARKDOWN_INT = "42"
    EXPECTED_RENDERED_HTML_INT = "42"
    EXPECTED_RENDERED_JSON_INT = '{"number": 42}'
    EXPECTED_RENDERED_FOR_PROMPT_INT = "42"

    # Expected outputs for render methods - float
    EXPECTED_RENDERED_PLAIN_FLOAT = "3.14159"
    EXPECTED_RENDERED_MARKDOWN_FLOAT = "3.14159"
    EXPECTED_RENDERED_HTML_FLOAT = "3.14159"
    EXPECTED_RENDERED_JSON_FLOAT = '{"number": 3.14159}'
    EXPECTED_RENDERED_FOR_PROMPT_FLOAT = "3.14159"
