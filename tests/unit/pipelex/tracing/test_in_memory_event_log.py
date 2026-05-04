"""Tests for InMemoryEventLog."""

from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from tests.unit.pipelex.tracing.conftest import make_trace_event


class TestInMemoryEventLog:
    """Tests for the in-memory event log backend."""

    def test_emit_and_read_back(self) -> None:
        """Events survive an emit/read cycle with correct order and content."""
        event_log = InMemoryEventLog()
        events = [make_trace_event(sequence=idx) for idx in range(3)]
        for evt in events:
            event_log.emit(evt)

        result = event_log.read_events("run_001")

        assert len(result) == 3
        for idx, read_event in enumerate(result):
            assert read_event.sequence == idx
            assert read_event.workflow_id == "wf_abc"

    def test_deduplication(self) -> None:
        """Duplicate (workflow_id, sequence) pairs are deduplicated, keeping first."""
        event_log = InMemoryEventLog()
        event_a = make_trace_event(sequence=0)
        event_b = make_trace_event(sequence=0)
        event_log.emit(event_a)
        event_log.emit(event_b)

        result = event_log.read_events("run_001")

        assert len(result) == 1
        assert result[0] is event_a

    def test_cleanup_removes_events(self) -> None:
        """Cleanup removes events for one run but preserves others."""
        event_log = InMemoryEventLog()
        event_log.emit(make_trace_event(pipeline_run_id="run_001"))
        event_log.emit(make_trace_event(pipeline_run_id="run_002"))

        event_log.cleanup("run_001")

        assert len(event_log.read_events("run_001")) == 0
        assert len(event_log.read_events("run_002")) == 1

    def test_read_nonexistent_run(self) -> None:
        """Reading a nonexistent pipeline_run_id returns an empty list."""
        event_log = InMemoryEventLog()

        result = event_log.read_events("nonexistent_run")

        assert result == []

    def test_multiple_workflows_sorted(self) -> None:
        """Events from multiple workflows are returned sorted by (workflow_id, sequence)."""
        event_log = InMemoryEventLog()
        event_log.emit(make_trace_event(workflow_id="wf_zzz", sequence=0))
        event_log.emit(make_trace_event(workflow_id="wf_aaa", sequence=1))
        event_log.emit(make_trace_event(workflow_id="wf_aaa", sequence=0))

        result = event_log.read_events("run_001")

        assert len(result) == 3
        assert result[0].workflow_id == "wf_aaa"
        assert result[0].sequence == 0
        assert result[1].workflow_id == "wf_aaa"
        assert result[1].sequence == 1
        assert result[2].workflow_id == "wf_zzz"
        assert result[2].sequence == 0
