import asyncio
import contextlib
import contextvars
import os
import threading
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, ParamSpec, TypeVar, cast

_T = TypeVar("_T")
_P = ParamSpec("_P")


def is_event_loop_running_on_this_thread() -> bool:
    """Whether the calling thread is running an event loop, which a blocking call would hold up."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


class WorkerThreads:
    """A named pool of at most ``max_workers`` worker threads, which runs blocking calls off the event loop.

    The pool starts its threads as calls need them. A call made while every thread is busy waits for one to free, its
    caller awaiting on the event loop meanwhile, never blocking it. A process forked from one whose pool had started
    threads starts a pool of its own, since a forked child holds none of its parent's threads.
    """

    def __init__(self, *, name: str, max_workers: int) -> None:
        self.name = name
        self.max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None
        self._executor_lock = threading.Lock()
        if hasattr(os, "register_at_fork"):
            os.register_at_fork(after_in_child=self._forget_parent_executor)

    def _forget_parent_executor(self) -> None:
        self._executor = None
        self._executor_lock = threading.Lock()

    def _executor_of_this_process(self) -> ThreadPoolExecutor:
        with self._executor_lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix=self.name)
            return self._executor

    async def run(self, func: Callable[_P, _T], /, *args: _P.args, **kwargs: _P.kwargs) -> _T:
        """Run a blocking call in one of the pool's threads and return its result.

        The call runs in a copy of the caller's context, as ``asyncio.to_thread`` runs one, so it reads the caller's
        context variables, such as the current library, the caller's identity or the log context. What the call sets in
        them stays in that copy: a binding the caller reads afterwards is one the caller makes itself.

        A thread cannot be interrupted, so a cancellation of the caller never counts the call as over while its thread
        still runs. The call is submitted to the pool's executor, and what this waits for is the executor's own future of
        it, never a task of the event loop, which the shutdown of ``asyncio.run`` would cancel along with the caller. A
        call no thread has taken yet is withdrawn and never runs; a call already running is waited for until it ends
        before the cancellation goes through, a cancellation repeated meanwhile included. The caller's own cleanup, such
        as tearing down the library the call was loading into, therefore never runs while the call is still at work on
        what it cleans up. The call's result or error is then dropped, since no caller is left to take it.
        """
        call_context = contextvars.copy_context()

        def call_in_the_callers_context() -> _T:
            return call_context.run(func, *args, **kwargs)

        thread_future = self._executor_of_this_process().submit(call_in_the_callers_context)
        outcome = asyncio.wrap_future(thread_future)
        try:
            return await asyncio.shield(outcome)
        except asyncio.CancelledError:
            # A call no thread has taken yet is withdrawn: it never runs, so its future is done at once.
            thread_future.cancel()
            outcome.add_done_callback(_drop_outcome)
            while not thread_future.done():
                # A cancellation repeated while the call ends changes nothing: the call cannot be stopped either way.
                # `outcome` mirrors the executor's future and is done only once that future is.
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait({outcome})
            raise


def _drop_outcome(  # kw-only: ignore
    outcome: asyncio.Future[Any],
) -> None:
    """Retrieve a dropped call's error, which keeps asyncio from logging it as never retrieved.

    A future's done-callback, which asyncio calls with the future as its one positional argument.
    """
    if not outcome.cancelled():
        outcome.exception()


async def _invoke(factory: Callable[[], Awaitable[_T]]) -> _T:
    """Call `factory` and await its result, both inside a coroutine.

    Calling `factory()` here — rather than where `gather` builds its arguments — means a
    factory that raises *synchronously* fails inside the gathered task. `asyncio.gather`
    with `return_exceptions=True` then captures that error like any other failure, instead
    of it propagating out before `gather` runs and orphaning the chunk's other coroutines.
    """
    return await factory()


async def gather_bounded(
    task_factories: Sequence[Callable[[], Awaitable[_T]]],
    *,
    max_concurrency: int | None,
) -> list[_T]:
    """Run `task_factories` in chunks with at most `max_concurrency` awaitables in flight at once.

    Each factory is called only when its chunk is about to run, so a factory that
    materializes an expensive resource — a deep-copied working memory, say — keeps at
    most `max_concurrency` of those resources alive at once. A bare `asyncio.Semaphore`
    over already-created coroutines would bound execution but not that materialization.

    A `max_concurrency` of `None`, or any value at least as large as the factory count,
    runs every factory in a single chunk (unbounded fan-out).

    Failure semantics are the same whether or not the run is bounded: within a chunk,
    every awaitable is awaited (drained) — never orphaned or cancelled — then the first
    error by input index is raised and no later chunk is started.

    Args:
        task_factories: Ordered callables, each returning a fresh awaitable when called.
        max_concurrency: Upper bound on awaitables in flight; `None` means unbounded.

    Returns:
        The awaited results, in the order of `task_factories`.

    Raises:
        ValueError: If `max_concurrency` is an int below 1.
    """
    if max_concurrency is not None and max_concurrency < 1:
        msg = f"gather_bounded requires max_concurrency to be a positive int or None, got {max_concurrency}"
        raise ValueError(msg)

    chunk_size = (len(task_factories) or 1) if max_concurrency is None else max_concurrency

    results: list[_T] = []
    for chunk_start in range(0, len(task_factories), chunk_size):
        chunk = task_factories[chunk_start : chunk_start + chunk_size]
        chunk_outcomes = await asyncio.gather(*(_invoke(factory) for factory in chunk), return_exceptions=True)
        for outcome in chunk_outcomes:
            if isinstance(outcome, BaseException):
                raise outcome
        # The loop above proved every outcome in this chunk is a real result, not an exception.
        results.extend(cast("list[_T]", chunk_outcomes))
    return results
