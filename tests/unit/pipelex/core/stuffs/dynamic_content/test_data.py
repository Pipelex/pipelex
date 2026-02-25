from typing import Any, ClassVar

from pipelex.core.stuffs.dynamic_content import DynamicContent


class SampleDynamicContent(DynamicContent):
    """Test subclass for DynamicContent testing."""

    name: str
    value: int


class TestData:
    # Input content
    SAMPLE_NAME = "Dynamic Item"
    SAMPLE_VALUE = 100

    # Expected outputs for smart_dump
    EXPECTED_SMART_DUMP: ClassVar[dict[str, Any]] = {"name": "Dynamic Item", "value": 100}

    # Expected outputs for render methods
    # DynamicContent uses str(smart_dump()) for markdown and html
    EXPECTED_RENDERED_MARKDOWN = "{'name': 'Dynamic Item', 'value': 100}"
    EXPECTED_RENDERED_HTML = "{'name': 'Dynamic Item', 'value': 100}"
    EXPECTED_RENDERED_FOR_PROMPT = "{'name': 'Dynamic Item', 'value': 100}"
