import asyncio
import functools

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
        # An unbounded run (max_concurrency is None, or >= item_count) is a single chunk over every branch.
        if max_concurrency is None or max_concurrency >= item_count:
            assert probe.peak_in_flight == item_count, "unbounded run keeps every branch in flight at once"
        else:
            assert probe.peak_in_flight == max_concurrency, "a bounded run saturates the bound"

    async def test_unbounded_run_propagates_lowest_index_error_over_a_faster_one(self) -> None:
        """In a single (unbounded) chunk, the lowest input index wins even though it fails later."""
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

    async def test_failing_chunk_is_drained_lowest_index_wins_and_later_chunks_skipped(self) -> None:
        """The failing chunk is fully awaited, its lowest-index error wins, and no later chunk starts."""
        probe = _ConcurrencyProbe()
        # max_concurrency=2 → chunks [0,1] [2,3] [4,5]; both branches of the second chunk fail.
        factories = [functools.partial(probe.run, index) for index in range(6)]
        factories[2] = functools.partial(probe.fail, 2, 0.05)  # lower index, fails slower
        factories[3] = functools.partial(probe.fail, 3, 0.01)  # higher index, fails faster

        with pytest.raises(ValueError, match="branch 2 failed"):
            await gather_bounded(factories, max_concurrency=2)

        assert probe.ran_indices == {0, 1, 2, 3}, "the failing chunk is drained (2 and 3 both run) and no later chunk starts (4, 5 never run)"

    @pytest.mark.parametrize("bad_max_concurrency", [0, -1])
    async def test_non_positive_max_concurrency_is_rejected(self, bad_max_concurrency: int) -> None:
        """A non-positive int bound is a caller error — `None` is the only way to ask for unbounded."""
        factories = [functools.partial(_ConcurrencyProbe().run, index) for index in range(3)]

        with pytest.raises(ValueError, match="positive int or None"):
            await gather_bounded(factories, max_concurrency=bad_max_concurrency)
