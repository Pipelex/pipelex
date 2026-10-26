"""The S3 client each event loop opens once and shares, and when it is closed.

These tests run their own event loops, as a command line running each step under `asyncio.run` does, so they can watch
a client outlive one operation, stay out of another loop, and close as its loop shuts down or the provider tears down.
"""

import asyncio
from typing import Any, NamedTuple

import pytest
from botocore.exceptions import NoRegionError
from pytest_mock import MockerFixture

from pipelex.tools.storage.s3_storage_provider import S3StorageProvider
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME

_URI = f"{PIPELEX_STORAGE_SCHEME}scope/blobs/abc"


class _ClientEvent(NamedTuple):
    kind: str
    loop: asyncio.AbstractEventLoop


class _RecordingSession:
    """An aiobotocore session whose clients record, on the loop they run on, when they open and when they close."""

    def __init__(self, *, mocker: MockerFixture, failing_opens: int = 0, failing_closes: int = 0) -> None:
        self._mocker = mocker
        self.failing_opens = failing_opens
        self.failing_closes = failing_closes
        self.events: list[_ClientEvent] = []

    def kinds(self) -> list[str]:
        return [event.kind for event in self.events]

    def create_client(self, **_config: Any) -> Any:
        session = self
        client = self._mocker.AsyncMock()
        client.head_object = self._mocker.AsyncMock(return_value={"ContentLength": 3})

        class _ClientContext:
            async def __aenter__(self) -> Any:
                # Yield, so operations starting together all reach the opening before it ends.
                await asyncio.sleep(0)
                if session.failing_opens > 0:
                    session.failing_opens -= 1
                    raise NoRegionError
                session.events.append(_ClientEvent(kind="open", loop=asyncio.get_running_loop()))
                return client

            async def __aexit__(self, *_exc_info: object) -> None:
                if session.failing_closes > 0:
                    session.failing_closes -= 1
                    msg = "The connection could not be closed"
                    raise OSError(msg)
                session.events.append(_ClientEvent(kind="close", loop=asyncio.get_running_loop()))

        return _ClientContext()


def _make_provider() -> S3StorageProvider:
    return S3StorageProvider(bucket_name="test-bucket", region="us-east-1", signed_urls_lifespan=None)


class TestS3StorageProviderClientReuse:
    @pytest.fixture
    def session(self, mocker: MockerFixture) -> _RecordingSession:
        recording_session = _RecordingSession(mocker=mocker)
        mocker.patch("aiobotocore.session.get_session", return_value=recording_session)
        return recording_session

    def test_operations_on_one_loop_share_one_client_closed_as_the_loop_shuts_down(self, session: _RecordingSession) -> None:
        provider = _make_provider()
        loops: list[asyncio.AbstractEventLoop] = []

        async def _operate() -> None:
            loops.append(asyncio.get_running_loop())
            for _ in range(3):
                assert await provider.load_size(uri=_URI) == 3
            assert session.kinds() == ["open"]

        asyncio.run(_operate())

        assert session.events == [_ClientEvent(kind="open", loop=loops[0]), _ClientEvent(kind="close", loop=loops[0])]

    def test_operations_starting_together_open_one_client(self, session: _RecordingSession) -> None:
        provider = _make_provider()

        async def _operate() -> None:
            sizes = await asyncio.gather(*[provider.load_size(uri=_URI) for _ in range(8)])
            assert sizes == [3] * 8

        asyncio.run(_operate())

        assert session.kinds() == ["open", "close"]

    def test_each_loop_opens_its_own_client_and_closes_it_on_itself(self, session: _RecordingSession) -> None:
        """An aiobotocore client belongs to the loop that opened it, so a second loop never reuses the first one's."""
        provider = _make_provider()
        loops: list[asyncio.AbstractEventLoop] = []

        async def _operate() -> None:
            loops.append(asyncio.get_running_loop())
            await provider.load_size(uri=_URI)

        asyncio.run(_operate())
        asyncio.run(_operate())

        assert session.events == [
            _ClientEvent(kind="open", loop=loops[0]),
            _ClientEvent(kind="close", loop=loops[0]),
            _ClientEvent(kind="open", loop=loops[1]),
            _ClientEvent(kind="close", loop=loops[1]),
        ]

    def test_teardown_on_the_running_loop_closes_its_client_soon_after(self, session: _RecordingSession) -> None:
        """A server tears the runtime down from its own loop: the close is scheduled there, and a later operation reopens."""
        provider = _make_provider()

        async def _operate() -> None:
            await provider.load_size(uri=_URI)
            provider.teardown()
            assert session.kinds() == ["open"]
            for _ in range(5):
                await asyncio.sleep(0)
            assert session.kinds() == ["open", "close"]
            await provider.load_size(uri=_URI)
            assert session.kinds() == ["open", "close", "open"]

        asyncio.run(_operate())

        assert session.kinds() == ["open", "close", "open", "close"]

    def test_teardown_closes_the_client_of_a_loop_no_longer_running(self, session: _RecordingSession) -> None:
        provider = _make_provider()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(provider.load_size(uri=_URI))
            assert session.kinds() == ["open"]

            provider.teardown()

            assert session.events == [_ClientEvent(kind="open", loop=loop), _ClientEvent(kind="close", loop=loop)]
        finally:
            loop.close()

    def test_a_close_failing_on_a_stopped_loop_is_logged_and_the_other_loops_clients_still_close(self, mocker: MockerFixture) -> None:
        """The runtime's teardown must never fail, so a client that cannot be closed does not keep the next one open."""
        failing_session = _RecordingSession(mocker=mocker, failing_closes=1)
        mocker.patch("aiobotocore.session.get_session", return_value=failing_session)
        log_debug = mocker.patch("pipelex.tools.storage.s3_storage_provider.log.debug")
        provider = _make_provider()
        first_loop = asyncio.new_event_loop()
        second_loop = asyncio.new_event_loop()
        try:
            first_loop.run_until_complete(provider.load_size(uri=_URI))
            second_loop.run_until_complete(provider.load_size(uri=_URI))

            provider.teardown()

            assert failing_session.events == [
                _ClientEvent(kind="open", loop=first_loop),
                _ClientEvent(kind="open", loop=second_loop),
                _ClientEvent(kind="close", loop=second_loop),
            ]
            log_debug.assert_called_once()
            assert log_debug.call_args.args == ("An S3 client could not be closed",)
        finally:
            first_loop.close()
            second_loop.close()

    def test_a_close_failing_on_the_running_loop_is_logged(self, mocker: MockerFixture) -> None:
        failing_session = _RecordingSession(mocker=mocker, failing_closes=1)
        mocker.patch("aiobotocore.session.get_session", return_value=failing_session)
        log_debug = mocker.patch("pipelex.tools.storage.s3_storage_provider.log.debug")
        provider = _make_provider()

        async def _operate() -> None:
            await provider.load_size(uri=_URI)
            provider.teardown()
            for _ in range(5):
                await asyncio.sleep(0)
            log_debug.assert_called_once()
            assert log_debug.call_args.args == ("An S3 client could not be closed",)

        asyncio.run(_operate())

        assert failing_session.kinds() == ["open"]

    def test_teardown_leaves_a_closed_loop_s_client_alone(self, session: _RecordingSession) -> None:
        """A loop closed without shutting its generators down left its client open, and nothing can run its close any more."""
        provider = _make_provider()
        loop = asyncio.new_event_loop()
        loop.run_until_complete(provider.load_size(uri=_URI))
        loop.close()

        provider.teardown()

        assert session.kinds() == ["open"]

    def test_a_client_that_failed_to_open_is_opened_again_by_the_next_operation(self, mocker: MockerFixture) -> None:
        failing_session = _RecordingSession(mocker=mocker, failing_opens=1)
        mocker.patch("aiobotocore.session.get_session", return_value=failing_session)
        provider = _make_provider()

        async def _operate() -> None:
            with pytest.raises(NoRegionError):
                await provider.load_size(uri=_URI)
            assert await provider.load_size(uri=_URI) == 3

        asyncio.run(_operate())

        assert failing_session.kinds() == ["open", "close"]
