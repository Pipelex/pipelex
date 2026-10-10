import asyncio

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
    await asyncio.Event().wait()


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
