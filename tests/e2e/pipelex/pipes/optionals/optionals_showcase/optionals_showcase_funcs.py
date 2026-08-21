"""PipeFunc implementations for the optionals showcase bundle, auto-registered at library load
via the @pipe_func decorator (FuncRegistryUtils.register_funcs_in_folder).
"""

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
async def oshow_analyze_clause(working_memory: WorkingMemory) -> TextContent:  # ruff: ignore[unused-async]
    return TextContent(text=f"analysis of {working_memory.get_stuff_as_str(name='clause')}")


@pipe_func()
async def oshow_summarize_analysis(working_memory: WorkingMemory) -> TextContent:  # ruff: ignore[unused-async]
    return TextContent(text=f"summary: {working_memory.get_stuff_as_str(name='analysis')}")


@pipe_func()
async def oshow_flag_risk(working_memory: WorkingMemory) -> TextContent:  # ruff: ignore[unused-function-argument, unused-async]
    return TextContent(text="penalty risk detected")


@pipe_func()
async def oshow_force_extract(working_memory: WorkingMemory) -> TextContent:  # ruff: ignore[unused-async]
    return TextContent(text=f"extracted: {working_memory.get_stuff_as_str(name='clause')}")
