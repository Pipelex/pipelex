from typing import Any, ClassVar

from pipelex.core.stuffs.text_content import TextContent


class TestData:
    # Input content - list of TextContent
    SAMPLE_TEXT_ITEMS: ClassVar[list[TextContent]] = [
        TextContent(text="Item 1"),
        TextContent(text="Item 2"),
        TextContent(text="Item 3"),
    ]

    # Expected outputs for smart_dump
    EXPECTED_SMART_DUMP: ClassVar[dict[str, Any]] = {
        "items": [
            {"text": "Item 1"},
            {"text": "Item 2"},
            {"text": "Item 3"},
        ]
    }

    # Expected outputs for render methods
    # ListContent renders TextContent items using their rendered_markdown() method
    EXPECTED_RENDERED_PLAIN = " • Item 1\n • Item 2\n • Item 3\n"
    EXPECTED_RENDERED_MARKDOWN = " • Item 1\n • Item 2\n • Item 3\n"
    EXPECTED_RENDERED_FOR_PROMPT = " • Item 1\n • Item 2\n • Item 3\n"

    # Empty list test cases
    EMPTY_ITEMS: ClassVar[list[TextContent]] = []
    EXPECTED_SMART_DUMP_EMPTY: ClassVar[dict[str, Any]] = {"items": []}
    EXPECTED_RENDERED_EMPTY = ""
