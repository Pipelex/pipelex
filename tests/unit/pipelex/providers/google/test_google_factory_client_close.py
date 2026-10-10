import asyncio
import gc
import weakref
from collections.abc import Coroutine
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.providers.google import google_factory
from pipelex.providers.google.google_factory import GoogleFactory
from pipelex.tools.log.error_fields import ERROR_MESSAGE_FIELD, ERROR_TYPE_FIELD


async def _close_failing() -> None:
    await asyncio.sleep(0)
    msg = "connection reset"
    raise ConnectionError(msg)


async def _close_succeeding() -> None:
    await asyncio.sleep(0)


async def _close_never_finishing() -> None:
    # The event is reachable only from this coroutine, so nothing outside the task waiting on it holds that task
    await asyncio.Event().wait()


def _schedule_and_find_close_task(*, close_coroutine: Coroutine[Any, Any, None]) -> "asyncio.Task[Any]":
    """Schedule a close on the running loop and return the task it created, which the scheduler does not return."""
    tasks_before = asyncio.all_tasks()
    GoogleFactory.schedule_client_close(event_loop=asyncio.get_running_loop(), close_coroutine=close_coroutine)
    (close_task,) = asyncio.all_tasks() - tasks_before
    return close_task


class TestGoogleFactoryScheduleClientClose:
    """The background task a worker's teardown schedules to close its Google async client."""

    @pytest.mark.asyncio
    async def test_a_pending_close_survives_garbage_collection_until_it_is_done(self) -> None:
        """The event loop holds a task only weakly, so a close task nothing else references would be collected mid-run."""
        close_task_ref = weakref.ref(_schedule_and_find_close_task(close_coroutine=_close_never_finishing()))
        await asyncio.sleep(0)
        gc.collect()

        pending_close_task = close_task_ref()
        assert pending_close_task is not None
        assert not pending_close_task.done()

        pending_close_task.cancel()
        await asyncio.wait([pending_close_task])
        del pending_close_task
        gc.collect()

        assert close_task_ref() is None

    @pytest.mark.asyncio
    async def test_a_scheduled_close_that_fails_is_logged_with_its_error_as_fields(self, mocker: MockerFixture) -> None:
        debug = mocker.patch.object(google_factory.log, "debug")
        close_task = _schedule_and_find_close_task(close_coroutine=_close_failing())
        await asyncio.wait([close_task])

        debug.assert_called_once_with(
            "A Google async client could not be closed",
            fields={ERROR_TYPE_FIELD: "ConnectionError", ERROR_MESSAGE_FIELD: "connection reset"},
        )


class TestGoogleFactoryClientClose:
    """The done callback of the background task closing a Google async client at teardown."""

    @pytest.mark.asyncio
    async def test_a_failed_close_is_logged_with_its_error_as_fields(self, mocker: MockerFixture) -> None:
        debug = mocker.patch.object(google_factory.log, "debug")
        close_task = asyncio.create_task(_close_failing())
        await asyncio.wait([close_task])

        GoogleFactory.log_client_close_failure(close_task=close_task)

        debug.assert_called_once_with(
            "A Google async client could not be closed",
            fields={ERROR_TYPE_FIELD: "ConnectionError", ERROR_MESSAGE_FIELD: "connection reset"},
        )

    @pytest.mark.asyncio
    async def test_a_successful_close_logs_nothing(self, mocker: MockerFixture) -> None:
        debug = mocker.patch.object(google_factory.log, "debug")
        close_task = asyncio.create_task(_close_succeeding())
        await close_task

        GoogleFactory.log_client_close_failure(close_task=close_task)

        debug.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_cancelled_close_logs_nothing_and_does_not_raise(self, mocker: MockerFixture) -> None:
        """A cancelled task's `exception()` raises `CancelledError`, which must not escape the callback."""
        debug = mocker.patch.object(google_factory.log, "debug")
        close_task = asyncio.create_task(_close_never_finishing())
        await asyncio.sleep(0)
        close_task.cancel()
        await asyncio.wait([close_task])

        GoogleFactory.log_client_close_failure(close_task=close_task)

        debug.assert_not_called()
