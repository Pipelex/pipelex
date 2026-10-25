import asyncio
import threading
from contextvars import ContextVar

import pytest

from pipelex.tools.misc.async_utils import WorkerThreads, is_event_loop_running_on_this_thread

_PROBE: ContextVar[str | None] = ContextVar("worker_threads_probe", default=None)

#: How long a test waits for a thread to reach a point it signals, which bounds a regression's run.
_SIGNAL_TIMEOUT_SECONDS = 10.0
#: How long a test lets a cancellation settle before it checks that nothing went through.
_SETTLE_SECONDS = 0.05


def _describe_thread(*, label: str) -> tuple[str, bool, str | None, str]:
    """What the call saw where it ran: its label, whether a loop ran there, the probe's value, and its thread's name."""
    return label, is_event_loop_running_on_this_thread(), _PROBE.get(), threading.current_thread().name


def _set_the_probe(*, value: str) -> None:
    _PROBE.set(value)


def _refuse(*, message: str) -> None:
    raise ValueError(message)


class _HeldCall:
    """A blocking call that signals once it runs, then blocks until released, recording the order of what happens."""

    def __init__(self, *, events: list[str], name: str) -> None:
        self.events = events
        self.name = name
        self.started = threading.Event()
        self.release = threading.Event()

    def __call__(self) -> str:
        self.started.set()
        if not self.release.wait(timeout=_SIGNAL_TIMEOUT_SECONDS):
            msg = f"the held call '{self.name}' was never released"
            raise AssertionError(msg)
        self.events.append(f"{self.name} ended")
        return self.name


async def _abandon_a_running_call(*, threads: WorkerThreads, held_call: _HeldCall, events: list[str]) -> None:
    """Start a caller whose call blocks, then return while it runs, so `asyncio.run` cancels every task to shut down."""

    async def call_then_clean_up() -> None:
        try:
            await threads.run(held_call)
        finally:
            events.append("cleanup")

    caller = asyncio.create_task(call_then_clean_up())
    assert await asyncio.to_thread(held_call.started.wait, _SIGNAL_TIMEOUT_SECONDS), "the call never started"
    # Released from another thread a moment after the shutdown began cancelling the caller and every other task.
    threading.Timer(0.2, held_call.release.set).start()
    events.append(f"abandoned {caller.get_name()}")


@pytest.mark.asyncio(loop_scope="class")
class TestWorkerThreads:
    async def test_the_call_runs_in_a_named_thread_off_the_loop_with_the_callers_context(self) -> None:
        threads = WorkerThreads(name="pipelex-test-threads", max_workers=2)
        token = _PROBE.set("caller's value")
        try:
            label, ran_on_a_loop, probe_value, thread_name = await threads.run(_describe_thread, label="described")
        finally:
            _PROBE.reset(token)

        assert label == "described"
        assert ran_on_a_loop is False
        assert probe_value == "caller's value"
        assert thread_name.startswith("pipelex-test-threads")

    async def test_what_the_call_binds_stays_in_its_thread(self) -> None:
        await WorkerThreads(name="pipelex-test-threads", max_workers=1).run(_set_the_probe, value="the call's value")

        assert _PROBE.get() is None

    async def test_the_calls_error_reaches_the_caller(self) -> None:
        with pytest.raises(ValueError, match="refused in the worker thread"):
            await WorkerThreads(name="pipelex-test-threads", max_workers=1).run(_refuse, message="refused in the worker thread")

    async def test_a_call_waits_for_a_free_thread_beyond_the_bound(self) -> None:
        threads = WorkerThreads(name="pipelex-test-threads", max_workers=1)
        events: list[str] = []
        first = _HeldCall(events=events, name="first")
        second = _HeldCall(events=events, name="second")
        second.release.set()

        first_caller = asyncio.create_task(threads.run(first))
        assert await asyncio.to_thread(first.started.wait, _SIGNAL_TIMEOUT_SECONDS), "the first call never started"
        second_caller = asyncio.create_task(threads.run(second))
        await asyncio.sleep(_SETTLE_SECONDS)
        assert not second.started.is_set(), "a call ran beyond the pool's bound"

        first.release.set()
        assert await first_caller == "first"
        assert await second_caller == "second"
        assert events == ["first ended", "second ended"]

    async def test_a_cancelled_caller_waits_for_the_running_call_to_end(self) -> None:
        """A thread cannot be interrupted: the cancellation goes through once the call ends, a second one meanwhile included.

        So the caller's cleanup never runs while the call is still at work.
        """
        events: list[str] = []
        held_call = _HeldCall(events=events, name="held")
        caller = asyncio.create_task(WorkerThreads(name="pipelex-test-threads", max_workers=1).run(held_call))
        assert await asyncio.to_thread(held_call.started.wait, _SIGNAL_TIMEOUT_SECONDS), "the call never started"
        caller.cancel()
        await asyncio.sleep(_SETTLE_SECONDS)
        caller.cancel()
        await asyncio.sleep(_SETTLE_SECONDS)
        assert not caller.done(), "the cancellation went through while the call was still running"

        held_call.release.set()
        with pytest.raises(asyncio.CancelledError):
            await caller

        assert events == ["held ended"]

    async def test_a_cancelled_caller_withdraws_a_call_no_thread_has_taken(self) -> None:
        threads = WorkerThreads(name="pipelex-test-threads", max_workers=1)
        events: list[str] = []
        running = _HeldCall(events=events, name="running")
        queued = _HeldCall(events=events, name="queued")
        queued.release.set()

        running_caller = asyncio.create_task(threads.run(running))
        assert await asyncio.to_thread(running.started.wait, _SIGNAL_TIMEOUT_SECONDS), "the running call never started"
        queued_caller = asyncio.create_task(threads.run(queued))
        await asyncio.sleep(_SETTLE_SECONDS)
        queued_caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(queued_caller, timeout=_SIGNAL_TIMEOUT_SECONDS)

        running.release.set()
        assert await running_caller == "running"
        assert not queued.started.is_set(), "a withdrawn call ran"
        assert events == ["running ended"]

    async def test_the_shutdown_of_asyncio_run_waits_for_the_running_call_before_the_cleanup(self) -> None:
        """`asyncio.run` cancels the caller and every other task at once; the call's end still comes before the cleanup."""
        threads = WorkerThreads(name="pipelex-test-threads", max_workers=1)
        events: list[str] = []
        held_call = _HeldCall(events=events, name="held")

        await asyncio.to_thread(asyncio.run, _abandon_a_running_call(threads=threads, held_call=held_call, events=events))

        assert events[1:] == ["held ended", "cleanup"], events
