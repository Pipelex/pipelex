import asyncio
import functools
from collections.abc import Awaitable, Callable

import pytest

from pipelex.tools.misc.async_utils import gather_bounded


class _ConcurrencyProbe:
    """Tracks how many probe coroutines run at once and which indices ran."""

    def __init__(self) -> None:
        self.in_flight: int = 0
        self.peak_in_flight: int = 0
        self.ran_indices: set[int] = set()

    async def run(self, index: int, delay: float = 0.01) -> int:
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        self.ran_indices.add(index)
        await asyncio.sleep(delay)
        self.in_flight -= 1
        return index

    async def fail(self, index: int, delay: float = 0.01) -> int:
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        self.ran_indices.add(index)
        await asyncio.sleep(delay)
        self.in_flight -= 1
        msg = f"branch {index} failed"
        raise ValueError(msg)


@pytest.mark.asyncio(loop_scope="class")
class TestGatherBounded:
    @pytest.mark.parametrize(
        ("item_count", "max_concurrency"),
        [
            (10, 3),
            (100, 8),
            (7, 1),
            (5, 5),
            (3, 50),
            (4, None),
            (0, None),
        ],
    )
    async def test_peak_in_flight_never_exceeds_bound(self, item_count: int, max_concurrency: int | None) -> None:
        """No more than `max_concurrency` branches run at once; all items complete in input order."""
        probe = _ConcurrencyProbe()
        factories = [functools.partial(probe.run, index) for index in range(item_count)]

        results = await gather_bounded(factories, max_concurrency=max_concurrency)

        assert results == list(range(item_count)), "results must preserve input order"
        assert len(probe.ran_indices) == item_count, "every item must run exactly once"
        if max_concurrency is not None:
            assert probe.peak_in_flight <= max_concurrency, "in-flight count must never exceed max_concurrency"
        # An unbounded run (max_concurrency is None, or >= item_count) starts every branch at once.
        if max_concurrency is None or max_concurrency >= item_count:
            assert probe.peak_in_flight == item_count, "unbounded run keeps every branch in flight at once"
        else:
            assert probe.peak_in_flight == max_concurrency, "a bounded run saturates the bound"

    async def test_unbounded_run_propagates_lowest_index_error_over_a_faster_one(self) -> None:
        """In an unbounded run, the lowest input index wins even though it fails later."""
        probe = _ConcurrencyProbe()
        factories = [
            functools.partial(probe.run, 0),
            functools.partial(probe.fail, 1, 0.05),  # lower index, fails slower
            functools.partial(probe.run, 2),
            functools.partial(probe.fail, 3, 0.01),  # higher index, fails faster
            functools.partial(probe.run, 4),
        ]

        with pytest.raises(ValueError, match="branch 1 failed"):
            await gather_bounded(factories, max_concurrency=None)

    async def test_a_slow_item_does_not_hold_the_other_slots(self) -> None:
        """A slot that frees starts the next item at once: a slow item never holds back the items after it.

        Item 0 waits until the last item has finished, so it can end only if every other item ran while it was still
        running. Fixed chunks would never start the last item before item 0 ended, and the wait would time out.
        """
        item_count = 6
        last_item_done = asyncio.Event()
        start_order: list[int] = []

        async def slow_first() -> int:
            start_order.append(0)
            await last_item_done.wait()
            return 0

        async def fast(index: int) -> int:
            start_order.append(index)
            await asyncio.sleep(0)
            if index == item_count - 1:
                last_item_done.set()
            return index

        factories: list[Callable[[], Awaitable[int]]] = [slow_first]
        factories.extend(functools.partial(fast, index) for index in range(1, item_count))

        results = await asyncio.wait_for(gather_bounded(factories, max_concurrency=2), timeout=5)

        assert results == list(range(item_count)), "results must preserve input order"
        assert start_order == list(range(item_count)), "items start in input order"

    async def test_a_failure_stops_new_starts_and_lets_running_items_finish(self) -> None:
        """After a failure no item starts, every running item finishes, and the lowest-index failure is raised.

        With a window of 3, items 0, 1 and 2 start together. Item 2 fails first; items 0 and 1, still running, are not
        cancelled and finish, item 1 failing in turn. No later item starts, and item 1's error wins by input index.
        """
        probe = _ConcurrencyProbe()
        finished_indices: list[int] = []

        async def run_and_record(index: int, delay: float) -> int:
            result = await probe.run(index, delay)
            finished_indices.append(index)
            return result

        factories: list[Callable[[], Awaitable[int]]] = [functools.partial(run_and_record, index, 0.01) for index in range(6)]
        factories[0] = functools.partial(run_and_record, 0, 0.05)  # still running when item 2 fails
        factories[1] = functools.partial(probe.fail, 1, 0.03)  # lower index, fails after item 2
        factories[2] = functools.partial(probe.fail, 2, 0.01)  # higher index, fails first

        with pytest.raises(ValueError, match="branch 1 failed"):
            await gather_bounded(factories, max_concurrency=3)

        assert probe.ran_indices == {0, 1, 2}, "no item starts after the first failure"
        assert finished_indices == [0], "an item running when a sibling fails is not cancelled: it finishes"
        assert probe.in_flight == 0, "every started item has ended when the error is raised"

    async def test_items_started_before_a_failure_are_drained_in_a_sliding_window(self) -> None:
        """An item a freed slot started before the failure still finishes, and nothing starts after the failure.

        Window of 2: item 1 ends at once, so its slot starts item 2 while item 0 runs; item 0 fails only once item 2 has
        started, and item 2 ends only once item 0 has failed. Item 2 is drained, and items 3 and later never start. The
        steps are ordered by events rather than timers, so a stalled event loop cannot reorder them.
        """
        item_two_started = asyncio.Event()
        item_zero_failed = asyncio.Event()
        started_indices: list[int] = []
        finished_indices: list[int] = []

        async def fail_once_item_two_runs() -> int:
            started_indices.append(0)
            await item_two_started.wait()
            item_zero_failed.set()
            msg = "branch 0 failed"
            raise ValueError(msg)

        async def end_at_once(index: int) -> int:
            started_indices.append(index)
            await asyncio.sleep(0)
            finished_indices.append(index)
            return index

        async def end_once_item_zero_failed() -> int:
            started_indices.append(2)
            item_two_started.set()
            await item_zero_failed.wait()
            await asyncio.sleep(0)
            finished_indices.append(2)
            return 2

        factories: list[Callable[[], Awaitable[int]]] = [fail_once_item_two_runs, functools.partial(end_at_once, 1), end_once_item_zero_failed]
        factories.extend(functools.partial(end_at_once, index) for index in range(3, 6))

        with pytest.raises(ValueError, match="branch 0 failed"):
            await asyncio.wait_for(gather_bounded(factories, max_concurrency=2), timeout=5)

        assert started_indices == [0, 1, 2], "the freed slot started item 2 before item 0 failed, and no item starts after it"
        assert finished_indices == [1, 2], "item 2, running when item 0 failed, is drained before the error is raised"

    async def test_synchronous_factory_error_is_captured_and_running_items_are_drained(self) -> None:
        """A factory raising synchronously fails like any item: running items finish, none starts, lowest index wins."""
        probe = _ConcurrencyProbe()

        def sync_raiser(index: int) -> Awaitable[int]:
            msg = f"branch {index} raised synchronously"
            raise RuntimeError(msg)

        # A window of 4 starts items 0 to 3 together. Index 1 raises synchronously and index 3 fails asynchronously;
        # index 1 wins by input index. Indices 0, 2 and 3 still run to their end, and items 4 and 5 never start.
        factories: list[Callable[[], Awaitable[int]]] = [
            functools.partial(probe.run, 0),
            functools.partial(sync_raiser, 1),
            functools.partial(probe.run, 2),
            functools.partial(probe.fail, 3, 0.01),
            functools.partial(probe.run, 4),
            functools.partial(probe.run, 5),
        ]

        with pytest.raises(RuntimeError, match="branch 1 raised synchronously"):
            await gather_bounded(factories, max_concurrency=4)

        assert probe.ran_indices == {0, 2, 3}, "running items are drained despite the sync raise, and no later item starts"
        assert probe.in_flight == 0, "every started item has ended when the error is raised"

    @pytest.mark.parametrize("turns_between_ends", [0, 1])
    async def test_a_failure_one_turn_after_a_success_stops_new_starts(self, turns_between_ends: int) -> None:
        """A failure that ends a loop turn after a sibling's success still stops that sibling's slot from taking an item.

        The succeeding item's slot resumes a couple of loop steps after its item ends; a failure ending in between must
        already be recorded by then, so the failure is recorded in the very step that ends the failing item.
        """
        both_may_end = asyncio.Event()
        called_indices: list[int] = []

        async def succeed(index: int) -> int:
            called_indices.append(index)
            await both_may_end.wait()
            return index

        async def fail_later(index: int) -> int:
            called_indices.append(index)
            await both_may_end.wait()
            for _ in range(turns_between_ends):
                await asyncio.sleep(0)
            msg = f"branch {index} failed"
            raise ValueError(msg)

        factories: list[Callable[[], Awaitable[int]]] = [
            functools.partial(succeed, 0),
            functools.partial(fail_later, 1),
            functools.partial(succeed, 2),
        ]
        gathering = asyncio.ensure_future(gather_bounded(factories, max_concurrency=2))
        for _ in range(3):
            await asyncio.sleep(0)
        both_may_end.set()

        with pytest.raises(ValueError, match="branch 1 failed"):
            await gathering

        assert called_indices == [0, 1], "no factory is called once a failure has ended"

    async def test_a_cancelled_caller_resumes_only_once_every_running_item_has_cleaned_up(self) -> None:
        """A cancellation reaches the caller only after every running item has finished its own cleanup.

        The caller's own teardown, such as closing what the items work on, must never run under an item still cleaning up.
        """
        cleaned_up: list[int] = []
        cleanup_delays = {0: 0.001, 1: 0.05}

        async def wait_then_clean_up(index: int) -> int:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await asyncio.sleep(cleanup_delays[index])
                cleaned_up.append(index)
                raise
            return index

        factories = [functools.partial(wait_then_clean_up, index) for index in range(2)]
        gathering = asyncio.ensure_future(gather_bounded(factories, max_concurrency=2))
        for _ in range(3):
            await asyncio.sleep(0)
        gathering.cancel()

        with pytest.raises(asyncio.CancelledError):
            await gathering

        assert sorted(cleaned_up) == [0, 1], "the caller resumed while an item was still cleaning up"

    async def test_cancelling_the_caller_cancels_every_running_item(self) -> None:
        """A cancelled caller cancels the items in flight and starts none after them."""
        started_indices: list[int] = []
        cancelled_indices: list[int] = []

        async def wait_forever(index: int) -> int:
            started_indices.append(index)
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled_indices.append(index)
                raise
            return index

        factories = [functools.partial(wait_forever, index) for index in range(5)]
        gathering = asyncio.ensure_future(gather_bounded(factories, max_concurrency=2))
        for _ in range(3):
            await asyncio.sleep(0)
        gathering.cancel()

        with pytest.raises(asyncio.CancelledError):
            await gathering

        assert started_indices == [0, 1], "only the window's items started"
        assert sorted(cancelled_indices) == [0, 1], "every running item was cancelled with its caller"

    @pytest.mark.parametrize("bad_max_concurrency", [0, -1])
    async def test_non_positive_max_concurrency_is_rejected(self, bad_max_concurrency: int) -> None:
        """A non-positive int bound is a caller error — `None` is the only way to ask for unbounded."""
        factories = [functools.partial(_ConcurrencyProbe().run, index) for index in range(3)]

        with pytest.raises(ValueError, match="positive int or None"):
            await gather_bounded(factories, max_concurrency=bad_max_concurrency)
