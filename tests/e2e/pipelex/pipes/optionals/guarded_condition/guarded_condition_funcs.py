"""PipeFunc implementations for the guarded-condition bundle, auto-registered at library load via
the @pipe_func decorator (FuncRegistryUtils.register_funcs_in_folder).
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
