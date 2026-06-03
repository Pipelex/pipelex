"""Test functions registered for the runtime-bridge integration tests."""

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent


def mistralai_workflows_bridge_echo(working_memory: WorkingMemory) -> TextContent:
    """Echo the ``input_text`` stuff back as a TextContent output.

    Used by tests/integration/pipelex/runtime_bridge to validate end-to-end
    pipe execution through the bridge without invoking inference.
    """
    input_text = working_memory.get_stuff_as_str("input_text")
    return TextContent(text=input_text)
