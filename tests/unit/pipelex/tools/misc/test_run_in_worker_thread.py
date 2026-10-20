import asyncio
import threading
from contextvars import ContextVar

import pytest

from pipelex.tools.misc.async_utils import run_in_worker_thread

_PROBE: ContextVar[str | None] = ContextVar("run_in_worker_thread_probe", default=None)

#: How long a test waits for a thread to reach a point it signals, which bounds a regression's run.
_SIGNAL_TIMEOUT_SECONDS = 10.0


def _runs_an_event_loop() -> bool:
    """Whether the calling thread is running an event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _describe_thread(*, label: str) -> tuple[str, bool, str | None, int]:
    """What the call saw where it ran: its label, whether a loop ran there, the probe's value, and its thread."""
    return label, _runs_an_event_loop(), _PROBE.get(), threading.get_ident()


def _set_the_probe(*, value: str) -> None:
    _PROBE.set(value)


def _refuse(*, message: str) -> None:
    raise ValueError(message)


@pytest.mark.asyncio(loop_scope="class")
class TestRunInWorkerThread:
    async def test_the_call_runs_off_the_loop_with_the_callers_context(self) -> None:
        token = _PROBE.set("caller's value")
        try:
            label, ran_on_a_loop, probe_value, thread_id = await run_in_worker_thread(_describe_thread, label="described")
        finally:
            _PROBE.reset(token)

        assert label == "described"
        assert ran_on_a_loop is False
        assert probe_value == "caller's value"
        assert thread_id != threading.get_ident()

    async def test_what_the_call_binds_stays_in_its_thread(self) -> None:
        await run_in_worker_thread(_set_the_probe, value="the call's value")

        assert _PROBE.get() is None

    async def test_the_calls_error_reaches_the_caller(self) -> None:
        with pytest.raises(ValueError, match="refused in the worker thread"):
            await run_in_worker_thread(_refuse, message="refused in the worker thread")

    async def test_a_cancelled_caller_waits_for_the_call_to_end(self) -> None:
        """A thread cannot be interrupted: the cancellation goes through once the call ends, a second one meanwhile included.

        So the caller's cleanup never runs while the call is still at work.
        """
        started = threading.Event()
        release = threading.Event()
        ended = threading.Event()

        def blocking_call() -> str:
            started.set()
            if not release.wait(timeout=_SIGNAL_TIMEOUT_SECONDS):
                msg = "the blocking call was never released"
                raise AssertionError(msg)
            ended.set()
            return "dropped"

        caller = asyncio.create_task(run_in_worker_thread(blocking_call))
        assert await asyncio.to_thread(started.wait, _SIGNAL_TIMEOUT_SECONDS), "the call never started"
        caller.cancel()
        await asyncio.sleep(0.05)
        caller.cancel()
        await asyncio.sleep(0.05)
        assert not caller.done(), "the cancellation went through while the call was still running"

        release.set()
        with pytest.raises(asyncio.CancelledError):
            await caller

        assert ended.is_set()
