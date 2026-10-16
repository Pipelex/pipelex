"""The function of the `PipeFunc` call in flight in this context, for the in-process executor to run.

A `PipeFunc` step imports and checks its own function before it runs (`PipeFunc.bind_function`), and the executor it
hands the call to receives only the step's ref and `function_name`, the shape every executor shares, sandboxes
included. In `direct` mode the step holds the function the executor must run, and it may be a step no library holds,
such as one built from its blueprint by a programmatic caller: the step names the function it bound here, for the
duration of the call, and the in-process executor takes it from here before it looks the step up in the library.
"""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, NamedTuple


class _CallInFlight(NamedTuple):
    pipe_ref: str
    function: Callable[..., Any]


_CALL_IN_FLIGHT: ContextVar[_CallInFlight | None] = ContextVar("pipe_func_call_in_flight", default=None)


@contextmanager
def pipe_func_call_in_flight(*, pipe_ref: str, function: Callable[..., Any]) -> Generator[None]:
    """Name the function the step `pipe_ref` bound as the one its call runs, for the scope."""
    token = _CALL_IN_FLIGHT.set(_CallInFlight(pipe_ref=pipe_ref, function=function))
    try:
        yield
    finally:
        _CALL_IN_FLIGHT.reset(token)


def function_of_call_in_flight(*, pipe_ref: str) -> Callable[..., Any] | None:
    """The function the step `pipe_ref` bound for its call in flight in this context, or None when no such call is."""
    call_in_flight = _CALL_IN_FLIGHT.get()
    if call_in_flight is None or call_in_flight.pipe_ref != pipe_ref:
        return None
    return call_in_flight.function
