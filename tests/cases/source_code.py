"""Source code manipulation functions for testing."""

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import TextContent


def wrap_lines(working_memory: WorkingMemory) -> TextContent:
    """Wraps each line of source code text with HTML span tags.

    Args:
        working_memory: The working memory containing the source text

    Returns:
        TextContent with each line wrapped in span tags with class="line"

    """
    # Get the source text from working memory as string
    source_text = working_memory.get_stuff_as_str("source_text")

    # Split into lines and wrap each line
    lines = source_text.split("\n")
    wrapped_lines: list[str] = []

    for line in lines:
        wrapped_line = f'<span class="line">{line}</span>'
        wrapped_lines.append(wrapped_line)

    # Join back into a single string
    wrapped_text = "\n".join(wrapped_lines)

    return TextContent(text=wrapped_text)
