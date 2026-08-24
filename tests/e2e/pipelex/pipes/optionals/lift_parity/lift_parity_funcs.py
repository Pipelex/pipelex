"""PipeFunc implementations for the lift-parity bundle, auto-registered at library load via the
@pipe_func decorator (FuncRegistryUtils.register_funcs_in_folder).
"""

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
async def opar_make_analysis(working_memory: WorkingMemory) -> TextContent:  # ruff: ignore[unused-async]
    return TextContent(text=f"analysis of {working_memory.get_stuff_as_str(name='source')}")


@pipe_func()
async def opar_summarize(working_memory: WorkingMemory) -> TextContent:  # ruff: ignore[unused-async]
    return TextContent(text=f"summary: {working_memory.get_stuff_as_str(name='analysis')}")
