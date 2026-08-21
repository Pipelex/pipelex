"""Writer-id schema tests.

Pins the contract that every TraceEvent carries a writer_id field, that backends
expose a writer_id property, and that the read-side dedup/sort/file-routing keys
all incorporate writer_id correctly.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pytest_mock import MockerFixture

from pipelex.graph.graphspec import NodeKind
from pipelex.tracing.buffering_event_log import BufferingEventLog
from pipelex.tracing.dynamodb_event_log import DynamoDBEventLog
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from pipelex.tracing.trace_events import PipeStartEvent

_TS = datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC)
_PIPELINE_RUN_ID = "run_writer_id_001"
_WORKFLOW_ID = "wf_writer_id_xyz"


def _make_pipe_start(sequence: int, writer_id: str = "primary", workflow_id: str = _WORKFLOW_ID) -> PipeStartEvent:
    return PipeStartEvent(
        pipeline_run_id=_PIPELINE_RUN_ID,
        workflow_id=workflow_id,
        writer_id=writer_id,
        timestamp=_TS,
        sequence=sequence,
        node_id=f"g:{workflow_id}:node_{sequence}",
        pipe_code="pipe_x",
        pipe_type="PipeLLM",
        node_kind=NodeKind.OPERATOR,
    )


class TestWriterIdSchema:
    """Tests pinning the writer_id contract across TraceEvent and event log backends."""

    def test_trace_event_has_writer_id_default_primary(self) -> None:
        """A TraceEvent built without writer_id round-trips with writer_id="primary"."""
        event = PipeStartEvent(
            pipeline_run_id=_PIPELINE_RUN_ID,
            workflow_id=_WORKFLOW_ID,
            timestamp=_TS,
            sequence=0,
            node_id=f"g:{_WORKFLOW_ID}:node_0",
            pipe_code="pipe_x",
            pipe_type="PipeLLM",
            node_kind=NodeKind.OPERATOR,
        )

        json_str = event.model_dump_json()
        payload: dict[str, Any] = json.loads(json_str)

        assert payload["writer_id"] == "primary"
        restored = PipeStartEvent.model_validate_json(json_str)
        assert restored.writer_id == "primary"

    def test_legacy_ndjson_without_writer_id_field_reads_as_primary(self, tmp_path: Path) -> None:
        """An NDJSON line missing the writer_id field reads back with writer_id="primary".

        Pins backwards compatibility with files written before the writer_id field landed.
        """
        run_dir = tmp_path / _PIPELINE_RUN_ID
        run_dir.mkdir(parents=True)
        ndjson_file = run_dir / f"wf_{_WORKFLOW_ID}.ndjson"

        legacy_payload: dict[str, Any] = {
            "pipeline_run_id": _PIPELINE_RUN_ID,
            "workflow_id": _WORKFLOW_ID,
            "timestamp": _TS.isoformat(),
            "sequence": 0,
            "event_kind": "pipe_start",
            "node_id": f"g:{_WORKFLOW_ID}:node_0",
            "pipe_code": "pipe_x",
            "pipe_type": "PipeLLM",
            "node_kind": NodeKind.OPERATOR,
        }
        ndjson_file.write_text(json.dumps(legacy_payload) + "\n", encoding="utf-8")

        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        events = event_log.read_events(_PIPELINE_RUN_ID)

        assert len(events) == 1
        assert events[0].writer_id == "primary"

    def test_two_writers_same_workflow_dedup_keeps_both(self) -> None:
        """Read-side dedup distinguishes events by writer_id.

        Two events with same (workflow_id, type, sequence) but different writer_id
        must both survive dedup.
        """
        event_log = InMemoryEventLog()
        event_log.emit(_make_pipe_start(sequence=0, writer_id="a"))
        event_log.emit(_make_pipe_start(sequence=0, writer_id="b"))

        events = event_log.read_events(_PIPELINE_RUN_ID)
        writer_ids = {evt.writer_id for evt in events}

        assert len(events) == 2
        assert writer_ids == {"a", "b"}

    def test_ndjson_writer_id_in_filename_for_non_primary(self, tmp_path: Path) -> None:
        """NDJSON file naming includes writer_id when non-primary; legacy name when primary."""
        primary_log = NdjsonEventLog(traces_dir=str(tmp_path))
        runner_log = NdjsonEventLog(traces_dir=str(tmp_path), writer_id="act_pid42")

        primary_log.emit(_make_pipe_start(sequence=0))
        runner_log.emit(_make_pipe_start(sequence=0, writer_id="act_pid42"))

        run_dir = tmp_path / _PIPELINE_RUN_ID
        ndjson_files = sorted(path.name for path in run_dir.glob("*.ndjson"))

        assert ndjson_files == [f"wf_{_WORKFLOW_ID}.ndjson", f"wf_{_WORKFLOW_ID}__w_act_pid42.ndjson"]

    def test_two_writers_same_workflow_get_separate_handles(self, tmp_path: Path) -> None:
        """Two NdjsonEventLogs with different writer_ids must not share the file-handle cache slot.

        Pins the (pipeline_run_id, workflow_id, writer_id) cache key. With a 2-tuple key,
        the second writer would steal the first writer's file handle and corrupt routing.
        """
        log_a = NdjsonEventLog(traces_dir=str(tmp_path), writer_id="writer_a")
        log_b = NdjsonEventLog(traces_dir=str(tmp_path), writer_id="writer_b")

        log_a.emit(_make_pipe_start(sequence=0, writer_id="writer_a"))
        log_b.emit(_make_pipe_start(sequence=0, writer_id="writer_b"))
        log_a.close()
        log_b.close()

        run_dir = tmp_path / _PIPELINE_RUN_ID
        a_lines = (run_dir / f"wf_{_WORKFLOW_ID}__w_writer_a.ndjson").read_text(encoding="utf-8").splitlines()
        b_lines = (run_dir / f"wf_{_WORKFLOW_ID}__w_writer_b.ndjson").read_text(encoding="utf-8").splitlines()

        assert len(a_lines) == 1
        assert len(b_lines) == 1
        assert json.loads(a_lines[0])["writer_id"] == "writer_a"
        assert json.loads(b_lines[0])["writer_id"] == "writer_b"

    def test_ndjson_dedup_uses_writer_id(self, tmp_path: Path) -> None:
        """Read-side dedup for NDJSON keeps events with same (workflow_id, sequence) but different writer_id."""
        log_a = NdjsonEventLog(traces_dir=str(tmp_path), writer_id="writer_a")
        log_b = NdjsonEventLog(traces_dir=str(tmp_path), writer_id="writer_b")

        log_a.emit(_make_pipe_start(sequence=0, writer_id="writer_a"))
        log_b.emit(_make_pipe_start(sequence=0, writer_id="writer_b"))
        log_a.close()
        log_b.close()

        reader = NdjsonEventLog(traces_dir=str(tmp_path))
        events = reader.read_events(_PIPELINE_RUN_ID)

        assert len(events) == 2
        assert {evt.writer_id for evt in events} == {"writer_a", "writer_b"}

    def test_ndjson_sort_order_is_sequence_primary_writer_id_secondary(self, tmp_path: Path) -> None:
        """Sort order is (workflow_id, sequence, writer_id) — sequence is primary.

        Without this fix, sorting by (workflow_id, writer_id, sequence) would put
        runner-side `act_*` events before router-side `primary` events for the same
        workflow even though the router's events came earlier in time.
        """
        primary_log = NdjsonEventLog(traces_dir=str(tmp_path))
        runner_log = NdjsonEventLog(traces_dir=str(tmp_path), writer_id="act_x")

        # Emit out of order to exercise the sort.
        primary_log.emit(_make_pipe_start(sequence=2))
        runner_log.emit(_make_pipe_start(sequence=0, writer_id="act_x"))
        primary_log.emit(_make_pipe_start(sequence=1))
        primary_log.close()
        runner_log.close()

        reader = NdjsonEventLog(traces_dir=str(tmp_path))
        events = reader.read_events(_PIPELINE_RUN_ID)

        assert [evt.sequence for evt in events] == [0, 1, 2]
        assert events[0].writer_id == "act_x"
        assert events[1].writer_id == "primary"
        assert events[2].writer_id == "primary"

    def test_dynamodb_sk_includes_writer_id(self, mocker: MockerFixture) -> None:
        """DynamoDB SK encodes writer_id between workflow_id and sequence."""
        captured_items: list[dict[str, Any]] = []

        class _StubTable:
            def put_item(self, *, Item: dict[str, Any]) -> None:  # ruff: ignore[invalid-argument-name]  # boto3 kwarg name
                captured_items.append(Item)

        class _StubResource:
            @staticmethod
            def Table(_name: str) -> _StubTable:  # ruff: ignore[invalid-function-name]  # boto3 method name
                return _StubTable()

        mocker.patch(
            "pipelex.tracing.dynamodb_event_log.boto3.resource",
            return_value=_StubResource(),
        )

        event_log = DynamoDBEventLog(table_name="my_table", region="us-east-1", writer_id="act_pid42")
        event_log.emit(_make_pipe_start(sequence=0, writer_id="act_pid42"))

        assert len(captured_items) == 1
        assert captured_items[0]["SK"] == f"EVENT#{_WORKFLOW_ID}#act_pid42#0000000000"

    def test_event_log_exposes_writer_id_property(self, tmp_path: Path) -> None:
        """Every event log backend exposes its writer_id via a read-only property.

        Emitters use this to stamp writer_id at event construction time.
        """
        in_mem = InMemoryEventLog()
        ndjson = NdjsonEventLog(traces_dir=str(tmp_path), writer_id="act_x")
        buffering = BufferingEventLog()

        assert in_mem.writer_id == "primary"
        assert ndjson.writer_id == "act_x"
        assert buffering.writer_id == "primary"
