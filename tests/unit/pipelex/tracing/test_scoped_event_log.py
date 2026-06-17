"""Unit tests for the `scoped_event_log` ContextVar scope in `pipelex.hub`.

The scope lets a caller pin a specific `EventLogProtocol` instance for the duration
of a run so the write side (tracer emission) and the read side (tracing assembly)
share the SAME instance — the fix for the two-instance problem that an in-memory
event log cannot bridge via an external store.
"""

import asyncio

import pytest

from pipelex.hub import get_event_log_override, scoped_event_log
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.in_memory_event_log import InMemoryEventLog


class TestScopedEventLog:
    def test_override_set_and_restored(self):
        """Inside the scope the override is the given instance; outside it is None."""
        assert get_event_log_override() is None
        event_log = InMemoryEventLog()
        with scoped_event_log(event_log):
            assert get_event_log_override() is event_log
        assert get_event_log_override() is None

    def test_nesting_restores_outer_override(self):
        """An inner scope shadows the outer one and restores it on exit."""
        outer_log = InMemoryEventLog(writer_id="outer")
        inner_log = InMemoryEventLog(writer_id="inner")
        with scoped_event_log(outer_log):
            assert get_event_log_override() is outer_log
            with scoped_event_log(inner_log):
                assert get_event_log_override() is inner_log
            assert get_event_log_override() is outer_log
        assert get_event_log_override() is None

    def test_override_restored_on_exception(self):
        """The override is restored even when the scoped block raises."""
        event_log = InMemoryEventLog()

        def raise_inside_scope() -> None:
            with scoped_event_log(event_log):
                assert get_event_log_override() is event_log
                msg = "boom"
                raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="boom"):
            raise_inside_scope()
        assert get_event_log_override() is None

    @pytest.mark.asyncio
    async def test_concurrent_scopes_do_not_cross_contaminate(self):
        """Two concurrently-scoped tasks each see their own override (ContextVar isolation)."""
        log_alpha = InMemoryEventLog(writer_id="alpha")
        log_beta = InMemoryEventLog(writer_id="beta")
        observed: dict[str, EventLogProtocol | None] = {}

        async def scope_and_observe(event_log: EventLogProtocol, key: str) -> None:
            with scoped_event_log(event_log):
                await asyncio.sleep(0.01)
                observed[key] = get_event_log_override()
                await asyncio.sleep(0.01)

        await asyncio.gather(
            scope_and_observe(log_alpha, "alpha"),
            scope_and_observe(log_beta, "beta"),
        )

        assert observed["alpha"] is log_alpha
        assert observed["beta"] is log_beta
        assert get_event_log_override() is None
