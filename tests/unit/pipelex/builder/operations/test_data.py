"""Shared test data for pipelex.builder.operations tests."""

from typing import Any, ClassVar


class PipeOpsTestData:
    BASE_LLM_SPEC: ClassVar[dict[str, Any]] = {
        "pipe_code": "test_pipe",
        "description": "Test LLM pipe",
        "model": "$writing-creative",
        "inputs": {"text": "Text"},
        "output": "Text",
        "prompt": "Write about @text",
    }
