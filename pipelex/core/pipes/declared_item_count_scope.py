"""The scopes a host opens to bound what one request's dry run may build.

Two bounds share this context, both read through `pipelex.core.pipes.declared_item_count`, which falls back to the
deployment's configuration outside any scope:

- **The maximum declared item count**, the most items one slot may hold. A host opens
  :func:`scoped_max_declared_item_count` from a request's own maximum, such as a hosted plane from the caller's plan, and
  everything run in that context, the library load and the dry run's mock builders included, reads it.
- **The dry run's mock budget**, the most mock items one in-process dry run or one validation builds in all, whatever
  the slots. :func:`scoped_dry_run_mock_budget` opens one tally for the block, or joins the one already open, so a
  validation's sweep, a run's mock inputs and pipes, and the concurrent branches of a batch all add to the same tally.
  The tally lives in one process: each worker activity of a distributed dry run counts against a budget of its own.

This module reads no configuration, so the pipe machinery can open the scopes without importing the configuration
singleton: the budget's size is the configuration's, read when an item is added (`spend_dry_run_mock_items`).
"""

import threading
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from pipelex.core.pipes.declared_count_bounds import DECLARED_ITEM_COUNT_CEILING
from pipelex.system.exceptions import RunParameterError

_scoped_max_declared_item_count: ContextVar[int | None] = ContextVar("scoped_max_declared_item_count", default=None)


def validate_max_declared_item_count(*, value: int) -> int:
    """Refuse a maximum no runtime may set: below one, or past the parser's ceiling.

    A host states the maximum, so a value refused here is the host's bug, refused before any work. The deployment's own
    ceiling on a request's maximum is checked where a request's maximum enters
    (`pipelex.core.pipes.declared_item_count.validate_requested_max_declared_item_count`), since it reads the configuration.

    Raises:
        RunParameterError: The value is not a count between one and `DECLARED_ITEM_COUNT_CEILING`.
    """
    if isinstance(value, bool) or value < 1 or value > DECLARED_ITEM_COUNT_CEILING:
        msg = f"A maximum declared item count must be a whole number from 1 to {DECLARED_ITEM_COUNT_CEILING}, got {value!r}."
        raise RunParameterError(msg)
    return value


@contextmanager
def scoped_max_declared_item_count(*, maximum: int | None) -> Generator[None, None, None]:
    """Make `maximum` the maximum in force for the block; ``None`` keeps the one already in force.

    Raises:
        RunParameterError: `maximum` is not a count between one and `DECLARED_ITEM_COUNT_CEILING`.
    """
    if maximum is None:
        yield
        return
    token = _scoped_max_declared_item_count.set(validate_max_declared_item_count(value=maximum))
    try:
        yield
    finally:
        _scoped_max_declared_item_count.reset(token)


def get_scoped_max_declared_item_count() -> int | None:
    """The maximum a scope opened in this context states, or ``None`` outside every scope."""
    return _scoped_max_declared_item_count.get()


class DryRunMockTally:
    """The mock items one dry run has built so far, against the budget the configuration sets.

    The scope holds this one mutable object rather than a number, so every context copied from the scope's shares it:
    the concurrent branches of a batch, each run as a task in its own copy of the context, and a load's worker thread
    all add to the same tally, where a copied integer would give each of them a budget of its own. Under asyncio an add
    runs between two awaits, so no other coroutine interleaves with it; the lock makes it atomic across threads too.
    """

    def __init__(self) -> None:
        self._built = 0
        self._lock = threading.Lock()

    @property
    def built(self) -> int:
        """How many mock items the dry run has built so far."""
        return self._built

    def add_within(self, *, count: int, budget: int) -> bool:
        """Add `count` mock items when the tally stays within `budget`, and say whether it did; past it, add nothing."""
        with self._lock:
            if self._built + count > budget:
                return False
            self._built += count
            return True


_scoped_dry_run_mock_tally: ContextVar[DryRunMockTally | None] = ContextVar("scoped_dry_run_mock_tally", default=None)


@contextmanager
def scoped_dry_run_mock_budget(*, tally: DryRunMockTally | None = None) -> Generator[DryRunMockTally, None, None]:
    """Count the mock items the block builds against one budget: the one a scope around it opened, else `tally`, else a new one.

    A nested scope joins the open tally rather than starting a fresh one, so a validation's sweep and every pipe run in
    it, or a run's pipes and the branches of its batches, spend one budget between them.

    Args:
        tally: A tally opened before the block, outside any scope around it, such as the one a run's setup opened for
            its mock inputs and carried on the run's job (`PipeJob`), so the run's pipes spend the same budget.
    """
    open_tally = _scoped_dry_run_mock_tally.get()
    if open_tally is not None:
        yield open_tally
        return
    tally = tally or DryRunMockTally()
    token = _scoped_dry_run_mock_tally.set(tally)
    try:
        yield tally
    finally:
        _scoped_dry_run_mock_tally.reset(token)


def get_scoped_dry_run_mock_tally() -> DryRunMockTally | None:
    """The tally a budget scope opened in this context counts on, or ``None`` outside every one."""
    return _scoped_dry_run_mock_tally.get()
