import asyncio
import contextlib
import contextvars
import os
import threading
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, ParamSpec, TypeVar

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
    of it propagating out of the slot that called it.
    """
    return await factory()


async def gather_bounded(
    task_factories: Sequence[Callable[[], Awaitable[_T]]],
    *,
    max_concurrency: int | None,
) -> list[_T]:
    """Run `task_factories` through a sliding window of at most `max_concurrency` awaitables in flight at once.

    The window has `max_concurrency` slots. Each slot takes the next factory in input order, calls it and awaits it, then
    takes the next as soon as it is free, so one slow awaitable holds only its own slot and never the others. Each
    factory is called only when a slot takes it, so a factory that materializes an expensive resource — a copied
    working memory, say — keeps at most `max_concurrency` of those resources alive at once. A bare `asyncio.Semaphore`
    over already-created coroutines would bound execution but not that materialization.

    A `max_concurrency` of `None`, or any value at least as large as the factory count,
    starts every factory at once (unbounded fan-out).

    Failure semantics are the same whether or not the run is bounded: once an awaitable
    fails, no slot takes another factory, every awaitable already running is awaited to
    its end (drained) — never orphaned or cancelled — and the error of the lowest input
    index among those that failed is raised. Which factories ran depends only on the order
    in which the running awaitables end, so a replay that sees the same order of ends starts
    the same factories in the same order. A cancellation of the caller cancels every
    awaitable in flight.

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

    factory_count = len(task_factories)
    slot_count = factory_count if max_concurrency is None else min(max_concurrency, factory_count)
    outcomes: dict[int, _T | BaseException] = {}
    next_index = 0
    has_failed = False

    async def run_slot() -> None:
        nonlocal next_index, has_failed
        while not has_failed and next_index < factory_count:
            # Taken and advanced with no await in between, so no two slots ever take the same factory.
            factory_index = next_index
            next_index += 1
            # Gathering the one awaitable captures its error as its outcome, so the slot records it rather than dies.
            (outcome,) = await asyncio.gather(_invoke(task_factories[factory_index]), return_exceptions=True)
            outcomes[factory_index] = outcome
            if isinstance(outcome, BaseException):
                has_failed = True

    # The slots are started in order and each takes its first factory before its first await, so the first factories
    # start in input order. `asyncio.gather` with no `return_exceptions` cancels the slots, and through them every
    # awaitable in flight, when the caller is cancelled; a slot itself never raises.
    await asyncio.gather(*(run_slot() for _ in range(slot_count)))

    results: list[_T] = []
    for factory_index in sorted(outcomes):
        outcome = outcomes[factory_index]
        if isinstance(outcome, BaseException):
            raise outcome
        results.append(outcome)
    return results
