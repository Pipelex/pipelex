import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar, cast

_T = TypeVar("_T")


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
