"""Activity-side half of the Temporal error bridge.

A Temporal activity raises Pipelex exceptions; the workflow side re-wraps them
with ``TemporalError.from_app_error``. In between, Temporal's default failure
converter would auto-wrap a raw ``PipelexError`` without packing our structured
``ErrorReport`` into ``ApplicationError.details`` and without deriving
``non_retryable`` from the error's ``InferenceErrorCategory``.

``convert_pipelex_errors`` closes that gap: it converts a ``PipelexError`` to a
``TemporalError`` at the activity boundary so the category-aware retry decision
and the structured report survive into workflow code.
"""

import functools
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from pipelex.base_exceptions import PipelexError
from pipelex.temporal.tprl.temporal_error import TemporalError

_ActivityParams = ParamSpec("_ActivityParams")
_ActivityReturn = TypeVar("_ActivityReturn")


def convert_pipelex_errors(
    func: Callable[_ActivityParams, Awaitable[_ActivityReturn]],
) -> Callable[_ActivityParams, Awaitable[_ActivityReturn]]:
    """Convert any ``PipelexError`` raised by a Temporal activity into a ``TemporalError``.

    ``TemporalError.from_message_exception`` derives ``non_retryable`` from the
    error's ``InferenceErrorCategory`` and packs ``to_error_report()`` into
    ``ApplicationError.details`` — the structured data the workflow-side
    ``TemporalError.from_app_error`` then recovers.

    Apply this decorator *below* ``@activity.defn`` so Temporal registers the
    wrapped function; ``functools.wraps`` preserves the ``__name__`` and
    annotations Temporal inspects. Only ``PipelexError`` is caught — a non-Pipelex
    exception propagates untouched and Temporal's default converter handles it.

    Args:
        func: The async activity function to wrap.

    Returns:
        The wrapped async activity function.
    """

    @functools.wraps(func)
    async def wrapper(*args: _ActivityParams.args, **kwargs: _ActivityParams.kwargs) -> _ActivityReturn:
        try:
            return await func(*args, **kwargs)
        except PipelexError as exc:
            raise TemporalError.from_message_exception(exc=exc) from exc

    return wrapper
