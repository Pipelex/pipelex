"""PipeFunc implementations for the guarded-condition bundle, which names each by its import path from this folder,
such as `guarded_condition_funcs.<function>`.
"""

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
async def ogc_make_flagged_note(working_memory: WorkingMemory) -> TextContent:  # ruff: ignore[unused-function-argument, unused-async]
    return TextContent(text="flagged-branch")


@pipe_func()
async def ogc_make_plain_note(working_memory: WorkingMemory) -> TextContent:  # ruff: ignore[unused-function-argument, unused-async]
    return TextContent(text="plain-branch")
