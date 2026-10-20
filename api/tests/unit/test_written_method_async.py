import asyncio
import threading
from collections.abc import Mapping
from pathlib import Path

import pytest
from mthds.method_tree.models import MethodTree
from pipelex.libraries.written_trees import WRITTEN_METHOD_TREES, write_method_tree
from pytest_mock import MockerFixture

from pipelex_api.method_tree_request import RequestMethod, RequestTree, written_method_async

#: How long a test waits for a thread to reach a point it signals, which bounds a regression's run.
_SIGNAL_TIMEOUT_SECONDS = 10.0

_ECHO_MTHDS = b"""\
domain = "echo_demo"
main_pipe = "echo"

[pipe.echo]
type = "PipeCompose"
description = "Echo the data"
inputs = { data = "Text" }
output = "Text"
template = "$data"
"""

_REQUEST_METHOD = RequestMethod(tree=RequestTree.make_from_contents(contents={"main.mthds": _ECHO_MTHDS}), dependencies={})


def _runs_an_event_loop() -> bool:
    """Whether the calling thread is running an event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


class _RecordingWrite:
    """`write_method_tree`, noting each destination and whether its thread runs an event loop, then writing for real.

    Once ``hold`` is called, a write signals ``started`` and blocks until ``release`` is set, as a large tree's does.
    """

    def __init__(self) -> None:
        self.destinations: list[Path] = []
        self.writes_on_a_loop: list[bool] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def hold(self) -> None:
        self.release.clear()

    def __call__(self, *, contents: Mapping[str, bytes], destination: Path, expected_digest: str) -> MethodTree:
        self.destinations.append(destination)
        self.writes_on_a_loop.append(_runs_an_event_loop())
        self.started.set()
        if not self.release.wait(timeout=_SIGNAL_TIMEOUT_SECONDS):
            msg = "the held write was never released"
            raise AssertionError(msg)
        return write_method_tree(contents=contents, destination=destination, expected_digest=expected_digest)


@pytest.fixture(name="recording_write")
def recording_write_fixture(mocker: MockerFixture) -> _RecordingWrite:
    recording = _RecordingWrite()
    mocker.patch("pipelex_api.method_tree_request.write_method_tree", side_effect=recording)
    return recording


def _assert_removed_and_released(*, method_dir: Path) -> None:
    """The temporary directory the method was written into is gone, and no tree written there is held."""
    assert not method_dir.parent.exists()
    assert WRITTEN_METHOD_TREES.tree_written_at(directory=method_dir) is None


@pytest.mark.asyncio(loop_scope="class")
class TestWrittenMethodAsync:
    async def test_the_tree_is_written_off_the_event_loop_held_for_the_block_and_removed_after(self, recording_write: _RecordingWrite) -> None:
        async with written_method_async(request_method=_REQUEST_METHOD) as written:
            assert written.methods_dirs is None
            assert (written.method_dir / "main.mthds").read_bytes() == _ECHO_MTHDS
            assert WRITTEN_METHOD_TREES.tree_written_at(directory=written.method_dir) is written.tree

        assert recording_write.destinations == [written.method_dir]
        assert recording_write.writes_on_a_loop == [False]
        _assert_removed_and_released(method_dir=written.method_dir)

    async def test_a_failing_block_still_removes_the_tree(self, recording_write: _RecordingWrite) -> None:  # noqa: ARG002
        method_dirs: list[Path] = []

        async def fail_inside_the_block() -> None:
            async with written_method_async(request_method=_REQUEST_METHOD) as written:
                method_dirs.append(written.method_dir)
                msg = "the block failed"
                raise ValueError(msg)

        with pytest.raises(ValueError, match="the block failed"):
            await fail_inside_the_block()

        (method_dir,) = method_dirs
        _assert_removed_and_released(method_dir=method_dir)

    async def test_a_cancelled_block_still_removes_the_tree(self, recording_write: _RecordingWrite) -> None:  # noqa: ARG002
        method_dirs: list[Path] = []
        entered = asyncio.Event()

        async def hold_the_method_until_cancelled() -> None:
            async with written_method_async(request_method=_REQUEST_METHOD) as written:
                method_dirs.append(written.method_dir)
                entered.set()
                await asyncio.Event().wait()

        holder = asyncio.create_task(hold_the_method_until_cancelled())
        await asyncio.wait_for(entered.wait(), timeout=_SIGNAL_TIMEOUT_SECONDS)
        holder.cancel()
        with pytest.raises(asyncio.CancelledError):
            await holder

        (method_dir,) = method_dirs
        _assert_removed_and_released(method_dir=method_dir)

    async def test_a_cancellation_during_the_write_removes_the_tree_once_the_write_has_ended(self, recording_write: _RecordingWrite) -> None:
        """A thread cannot be interrupted, so the directory is removed only once the write is over, never under it."""
        recording_write.hold()

        async def hold_the_method() -> None:
            async with written_method_async(request_method=_REQUEST_METHOD):
                pytest.fail("the block ran although the write was cancelled")

        holder = asyncio.create_task(hold_the_method())
        assert await asyncio.to_thread(recording_write.started.wait, _SIGNAL_TIMEOUT_SECONDS), "the write never started"
        (method_dir,) = recording_write.destinations
        holder.cancel()
        await asyncio.sleep(0.05)
        assert not holder.done(), "the cancellation went through while the write was still running"
        assert method_dir.parent.exists(), "the directory was removed while the write was still running"

        recording_write.release.set()
        with pytest.raises(asyncio.CancelledError):
            await holder

        assert recording_write.writes_on_a_loop == [False]
        _assert_removed_and_released(method_dir=method_dir)
