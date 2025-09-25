import os
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest_asyncio
from pytest import FixtureRequest

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.hub import get_activity_manager
from pipelex.pipeline.activity.activity_handler import ActivityHandlerForResultFiles
from pipelex.tools.misc.file_utils import get_incremental_directory_path, remove_folder
from pipelex.tools.misc.json_utils import save_as_json_to_path
from tests.conftest import TEST_OUTPUTS_DIR


@pytest_asyncio.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def pipe_result_handler(request: FixtureRequest) -> AsyncIterator[tuple[str, ActivityHandlerForResultFiles]]:
    """This fixture is used to handle the result of a pipe run in unit tests.
    It creates and registers an activity handler to save the activities of the pipe into a specific directory.
    It returns a tuple with the result directory path and the activity handler, which enables the
    calling test to save whatever it wants into that result directory.
    """
    # Setup result handler
    pipe_code: str = request.node.callspec.params.get("pipe_code", "test_pipe") if hasattr(request.node, "callspec") else "test_pipe"  # type: ignore
    if not isinstance(pipe_code, str):
        raise RuntimeError(f"pipe_code is not a string: {pipe_code}")
    result_dir_path = get_incremental_directory_path(
        base_path=TEST_OUTPUTS_DIR,
        base_name=pipe_code,
    )
    activity_handler = ActivityHandlerForResultFiles(result_dir_path=result_dir_path)
    get_activity_manager().add_activity_callback(key="pipelex_unit_test", callback=activity_handler.handle_activity)

    yield result_dir_path, activity_handler

    # Cleanup after test
    get_activity_manager().remove_activity_callback(key="pipelex_unit_test")
    remove_folder(result_dir_path)


@pytest_asyncio.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def save_working_memory() -> Callable[[PipeOutput, str], Awaitable[None]]:
    async def _save_working_memory(pipe_output: PipeOutput, result_dir_path: str) -> None:
        pipe_output.working_memory.pretty_print()
        working_memory_path = os.path.join(result_dir_path, "working_memory.json")
        save_as_json_to_path(object_to_save=pipe_output.working_memory, path=working_memory_path)

    return _save_working_memory
