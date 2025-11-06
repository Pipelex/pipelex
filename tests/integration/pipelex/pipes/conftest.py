import os
from collections.abc import Awaitable, Callable

import pytest_asyncio

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.tools.misc.json_utils import save_as_json_to_path


@pytest_asyncio.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def save_working_memory() -> Callable[[PipeOutput, str], Awaitable[None]]:
    async def _save_working_memory(pipe_output: PipeOutput, result_dir_path: str) -> None:
        pipe_output.working_memory.pretty_print()
        working_memory_path = os.path.join(result_dir_path, "working_memory.json")
        save_as_json_to_path(object_to_save=pipe_output.working_memory, path=working_memory_path)

    return _save_working_memory
