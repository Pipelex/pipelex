from typing import Any, ClassVar


class TestData:
    # Input content
    SAMPLE_MERMAID_CODE = """graph TD
    A[Start] --> B{Decision}
    B -->|Yes| C[End]
    B -->|No| A"""
    SAMPLE_MERMAID_URL = "https://mermaid.live/edit#..."

    # Expected outputs for smart_dump
    EXPECTED_SMART_DUMP: ClassVar[dict[str, Any]] = {
        "mermaid_code": """graph TD
    A[Start] --> B{Decision}
    B -->|Yes| C[End]
    B -->|No| A""",
        "mermaid_url": "https://mermaid.live/edit#...",
    }

    # Expected outputs for render methods
    EXPECTED_RENDERED_PLAIN = """graph TD
    A[Start] --> B{Decision}
    B -->|Yes| C[End]
    B -->|No| A"""
    EXPECTED_RENDERED_MARKDOWN = """graph TD
    A[Start] --> B{Decision}
    B -->|Yes| C[End]
    B -->|No| A"""
    EXPECTED_RENDERED_HTML = '<div class="mermaid">graph TD\n    A[Start] --&gt; B{Decision}\n    B --&gt;|Yes| C[End]\n    B --&gt;|No| A</div>'
    EXPECTED_RENDERED_JSON = '{"mermaid": "graph TD\\n    A[Start] --> B{Decision}\\n    B -->|Yes| C[End]\\n    B -->|No| A"}'
    EXPECTED_RENDERED_FOR_PROMPT = """graph TD
    A[Start] --> B{Decision}
    B -->|Yes| C[End]
    B -->|No| A"""
