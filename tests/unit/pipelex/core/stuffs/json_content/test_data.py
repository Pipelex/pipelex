from typing import Any, ClassVar


class TestData:
    # Input content
    SAMPLE_JSON_OBJ: ClassVar[dict[str, Any]] = {"name": "John", "age": 30, "active": True}
    SAMPLE_NESTED_JSON_OBJ: ClassVar[dict[str, Any]] = {"user": {"name": "John", "email": "john@example.com"}, "count": 5}

    # Expected outputs for smart_dump
    EXPECTED_SMART_DUMP: ClassVar[dict[str, Any]] = {"json_obj": {"name": "John", "age": 30, "active": True}}
    EXPECTED_SMART_DUMP_NESTED: ClassVar[dict[str, Any]] = {"json_obj": {"user": {"name": "John", "email": "john@example.com"}, "count": 5}}

    # Expected outputs for render methods
    EXPECTED_RENDERED_PLAIN = """{
    "name": "John",
    "age": 30,
    "active": true
}"""
    EXPECTED_RENDERED_JSON = """{
    "name": "John",
    "age": 30,
    "active": true
}"""
    # convert_to_markdown produces headers for each key
    EXPECTED_RENDERED_MARKDOWN = "# name: John\n\n# age: 30\n\n# active: True"
    # rendered_for_prompt returns JSON format for JSONContent
    EXPECTED_RENDERED_FOR_PROMPT = """{
    "name": "John",
    "age": 30,
    "active": true
}"""

    # Empty object test cases
    EMPTY_JSON_OBJ: ClassVar[dict[str, Any]] = {}
    EXPECTED_SMART_DUMP_EMPTY: ClassVar[dict[str, Any]] = {"json_obj": {}}
