from typing import Any, ClassVar


class TestData:
    # Input content
    SAMPLE_TRUE = True
    SAMPLE_FALSE = False

    # Expected outputs for smart_dump
    EXPECTED_SMART_DUMP_TRUE: ClassVar[dict[str, Any]] = {"yes_no": True}
    EXPECTED_SMART_DUMP_FALSE: ClassVar[dict[str, Any]] = {"yes_no": False}

    # Expected outputs for render methods
    EXPECTED_RENDERED_PLAIN_TRUE = "yes"
    EXPECTED_RENDERED_PLAIN_FALSE = "no"
    EXPECTED_RENDERED_MARKDOWN_TRUE = "yes"
    EXPECTED_RENDERED_MARKDOWN_FALSE = "no"
    EXPECTED_RENDERED_HTML_TRUE = "yes"
    EXPECTED_RENDERED_HTML_FALSE = "no"
    EXPECTED_RENDERED_JSON_TRUE = '{"yes_no": true}'
    EXPECTED_RENDERED_JSON_FALSE = '{"yes_no": false}'
    EXPECTED_RENDERED_FOR_PROMPT_TRUE = "yes"
    EXPECTED_RENDERED_FOR_PROMPT_FALSE = "no"

    # Expected short_desc
    EXPECTED_SHORT_DESC_TRUE = "a yes/no answer (yes)"
    EXPECTED_SHORT_DESC_FALSE = "a yes/no answer (no)"

    # The field description is the LLM-facing generation contract.
    EXPECTED_FIELD_DESCRIPTION = "Whether the answer is yes (true) or no (false)."
