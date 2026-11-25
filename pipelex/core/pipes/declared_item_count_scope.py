"""The scope a host opens to state the maximum declared item count for one request.

A host opens :func:`scoped_max_declared_item_count` from a request's own maximum, such as a hosted plane from the
caller's plan, and everything run in that context, the library load and the dry run's mock builders included, reads it
through `pipelex.core.pipes.declared_item_count`, which falls back to the deployment's configuration outside any scope.

This module reads no configuration, so the pipe machinery can open the scope without importing the configuration
singleton.
"""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from pipelex.core.pipes.declared_count_bounds import DECLARED_ITEM_COUNT_CEILING
from pipelex.system.exceptions import RunParameterError

_scoped_max_declared_item_count: ContextVar[int | None] = ContextVar("scoped_max_declared_item_count", default=None)


def validate_max_declared_item_count(*, value: int) -> int:
    """Refuse a maximum no runtime may set: below one, or past the parser's ceiling.

    A host states the maximum, so a value refused here is the host's bug, refused before any work.

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
