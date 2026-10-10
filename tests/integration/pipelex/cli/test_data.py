from typing import ClassVar


class TruncatedCompletionRunTestData:
    """A method whose text step the model cannot finish: its completion stops at the output limit."""

    PIPE_CODE: ClassVar[str] = "write_summary"
    MODEL_HANDLE: ClassVar[str] = "stand-in-gpt"
    PARTIAL_TEXT: ClassVar[str] = "Cats are small carnivorous mammals that"

    MTHDS: ClassVar[str] = """
domain = "truncated_completion"
description = "A text step whose completion the model cannot finish"

[pipe.write_summary]
type = "PipeLLM"
description = "Summarize the topic"
inputs = { topic = "Text" }
output = "Text"
prompt = "Write a long summary about $topic"
"""
