from typing import List

from pipelex.core.stuff_content import TextContent
from pipelex.core.working_memory import WorkingMemory
from pipelex.tools.func_registry import func_registry


def wrap_lines(working_memory: WorkingMemory) -> TextContent:
    """
    Wraps each line of the source text in HTML span tags with class 'line'.

    Args:
        working_memory: The working memory containing the source text

    Returns:
        TextContent with each line wrapped in <span class="line">...</span>
    """
    # Get the source text from working memory
    source_text = working_memory.get_stuff_as_str("source_text")

    # Split the text into lines
    lines = source_text.split("\n")

    # Wrap each line in span tags
    wrapped_lines: List[str] = []
    for line in lines:
        wrapped_line = f'<span class="line">{line}</span>'
        wrapped_lines.append(wrapped_line)

    # Join the wrapped lines back together
    wrapped_text = "\n".join(wrapped_lines)

    return TextContent(text=wrapped_text)


def register_source_code_functions():
    """Register all source code processing functions."""
    func_registry.register_function(wrap_lines, name="wrap_lines")


# Auto-register functions when module is imported
register_source_code_functions()
