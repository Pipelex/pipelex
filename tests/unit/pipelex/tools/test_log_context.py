"""The run-scoped log context.

``with log.context(...)`` binds the run's identifiers onto a task-local context: nested bindings merge,
an absent identifier inherits rather than clears, the binding is released on exit however the block
ends, and two concurrent tasks never see each other's.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from pipelex import log
from pipelex.tools.log.log_context import LogContext, get_log_context


def _own_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """The records this test module emitted, whatever else the session's handlers saw."""
    return [record for record in caplog.records if record.name == __name__]


def _field(record: logging.LogRecord, *, name: str) -> Any:
    """A field carried on the record: an attribute the stdlib does not declare, read the way a sink reads it."""
    return getattr(record, name)


class TestLogContext:
    def test_context_yields_the_bound_context_and_restores_on_exit(self) -> None:
        assert get_log_context() is None
        with log.context(request_id="r1", pipeline_run_id="p1") as bound:
            assert bound == LogContext(request_id="r1", pipeline_run_id="p1")
            assert get_log_context() is bound
        assert get_log_context() is None

    def test_nested_contexts_merge_and_the_inner_overrides(self) -> None:
        with log.context(request_id="r1", pipeline_run_id="p1"):
            with log.context(pipeline_run_id="p2", pipe_run_id="pr1") as inner:
                assert inner == LogContext(request_id="r1", pipeline_run_id="p2", pipe_run_id="pr1")
            outer = get_log_context()
            assert outer == LogContext(request_id="r1", pipeline_run_id="p1")

    def test_a_none_identifier_inherits_rather_than_clears(self) -> None:
        with log.context(request_id="r1"), log.context(request_id=None, pipe_run_id="pr1") as inner:
            assert inner == LogContext(request_id="r1", pipe_run_id="pr1")

    def test_context_is_restored_when_the_block_raises(self) -> None:
        def explode() -> None:
            msg = "boom"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError), log.context(request_id="r1"):
            explode()
        assert get_log_context() is None

    def test_fields_of_a_context_omit_absent_identifiers(self) -> None:
        assert LogContext().fields == {}
        assert LogContext(pipeline_run_id="p1").fields == {"pipeline_run_id": "p1"}
        assert LogContext(request_id="r1", pipeline_run_id="p1", pipe_run_id="pr1").fields == {
            "request_id": "r1",
            "pipeline_run_id": "p1",
            "pipe_run_id": "pr1",
        }

    @pytest.mark.asyncio
    async def test_context_is_task_local(self, caplog: pytest.LogCaptureFixture) -> None:
        """Two concurrent tasks each see their own binding; neither leaks into the other or into the caller."""

        async def emit(request_id: str) -> None:
            with log.context(request_id=request_id):
                await asyncio.sleep(0)
                log.info("in task", fields={"tag": request_id})
                await asyncio.sleep(0)
                assert get_log_context() == LogContext(request_id=request_id)

        with caplog.at_level(logging.INFO):
            await asyncio.gather(emit("a"), emit("b"))

        assert get_log_context() is None
        records = _own_records(caplog)
        assert len(records) == 2
        for record in records:
            assert _field(record, name="request_id") == _field(record, name="tag")
