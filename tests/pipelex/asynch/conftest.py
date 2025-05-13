# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import os
from typing import AsyncGenerator, AsyncIterator, Awaitable, Callable

import pytest_asyncio
from pytest import FixtureRequest
from rich import print

from pipelex.activity_handler import ActivityHandlerForResultFiles
from pipelex.activity_manager import get_activity_manager
from pipelex.core.pipe_output import PipeOutput
from pipelex.pipe_works.pipe_router import PipeRouter
from pipelex.pipe_works.pipe_router_protocol import PipeRouterProtocol
from pipelex.tools.utils.json_utils import save_as_json_to_path
from pipelex.tools.utils.path_utils import get_incremental_directory_path


@pytest_asyncio.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def pipe_router(request: FixtureRequest) -> AsyncGenerator[PipeRouterProtocol, None]:
    # Code to run before each PipeRouter
    print("\n[magenta]PipeRouter setup[/magenta]")
    the_pipe_router = PipeRouter()
    # Return it for use in tests
    yield the_pipe_router
    # Code to run after each test
    print("\n[magenta]PipeRouter teardown[/magenta]")


@pytest_asyncio.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def pipe_result_handler(request: FixtureRequest) -> AsyncIterator[tuple[str, ActivityHandlerForResultFiles]]:
    """
    This fixture is used to handle the result of a pipe run in unit tests.
    It creates and registers an activity handler to save the activities of the pipe into a specific directory.
    It returns a tuple with the result directory path and the activity handler, which enables the
    calling test to save whatever it wants into that result directory.
    """
    # Setup result handler
    pipe_code: str = request.node.callspec.params.get("pipe_code", "test_pipe") if hasattr(request.node, "callspec") else "test_pipe"  # type: ignore
    if not isinstance(pipe_code, str):
        raise RuntimeError(f"pipe_code is not a string: {pipe_code}")
    result_dir_path = get_incremental_directory_path(
        base_path="results",
        base_name=pipe_code,
    )
    activity_handler = ActivityHandlerForResultFiles(result_dir_path=result_dir_path)
    get_activity_manager().add_activity_callback(key="pipelex_unit_test", callback=activity_handler.handle_activity)

    yield result_dir_path, activity_handler

    # Cleanup callback after test
    get_activity_manager().activity_callbacks.pop("pipelex_unit_test", None)


@pytest_asyncio.fixture  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def save_working_memory() -> Callable[[PipeOutput, str], Awaitable[None]]:
    async def _save_working_memory(pipe_output: PipeOutput, result_dir_path: str) -> None:
        pipe_output.working_memory.pretty_print()
        working_memory_path = os.path.join(result_dir_path, "working_memory.json")
        save_as_json_to_path(object_to_save=pipe_output.working_memory, path=working_memory_path)

    return _save_working_memory
