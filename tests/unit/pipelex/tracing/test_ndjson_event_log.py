"""Tests for NdjsonEventLog."""

import logging
import multiprocessing
from pathlib import Path

import pytest

from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from pipelex.tracing.trace_events import PipeStartEvent
from tests.unit.pipelex.tracing.conftest import make_trace_event


def _worker_fn(traces_dir: str, pipeline_run_id: str, workflow_id: str, num_events: int) -> None:
    """Write events from a subprocess. Must be module-level for macOS spawn."""
    event_log = NdjsonEventLog(traces_dir=traces_dir)
    for index_event in range(num_events):
        event = make_trace_event(
            workflow_id=workflow_id,
            sequence=index_event,
            pipeline_run_id=pipeline_run_id,
        )
        event_log.emit(event)
    event_log.close()


class TestNdjsonEventLog:
    """Tests for the NDJSON file-based event log backend."""

    def test_emit_and_read_back(self, tmp_path: Path) -> None:
        """Events survive an emit/read cycle with correct order and content."""
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        events = [make_trace_event(sequence=idx) for idx in range(3)]
        for evt in events:
            event_log.emit(evt)

        result = event_log.read_events("run_001")

        assert len(result) == 3
        for idx, read_event in enumerate(result):
            assert read_event.sequence == idx
            assert read_event.workflow_id == "wf_abc"
            assert isinstance(read_event, PipeStartEvent)
            assert read_event.pipe_code == "test_pipe"

    def test_deduplication(self, tmp_path: Path) -> None:
        """Duplicate (workflow_id, sequence) pairs are deduplicated."""
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(sequence=0))
        event_log.emit(make_trace_event(sequence=0))

        result = event_log.read_events("run_001")

        assert len(result) == 1

    def test_multiple_workflows(self, tmp_path: Path) -> None:
        """Events from multiple workflows are returned sorted by (workflow_id, sequence)."""
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(workflow_id="wf_zzz", sequence=0))
        event_log.emit(make_trace_event(workflow_id="wf_aaa", sequence=1))
        event_log.emit(make_trace_event(workflow_id="wf_aaa", sequence=0))
        event_log.emit(make_trace_event(workflow_id="wf_mmm", sequence=0))

        result = event_log.read_events("run_001")

        assert len(result) == 4
        assert result[0].workflow_id == "wf_aaa"
        assert result[0].sequence == 0
        assert result[1].workflow_id == "wf_aaa"
        assert result[1].sequence == 1
        assert result[2].workflow_id == "wf_mmm"
        assert result[3].workflow_id == "wf_zzz"

    def test_separate_files_per_workflow(self, tmp_path: Path) -> None:
        """Each workflow_id gets its own NDJSON file."""
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(workflow_id="wf_alpha", sequence=0))
        event_log.emit(make_trace_event(workflow_id="wf_beta", sequence=0))

        run_dir = tmp_path / "run_001"
        ndjson_files = sorted(run_dir.glob("*.ndjson"))
        assert len(ndjson_files) == 2
        assert ndjson_files[0].name == "wf_wf_alpha.ndjson"
        assert ndjson_files[1].name == "wf_wf_beta.ndjson"

    def test_cleanup_removes_directory(self, tmp_path: Path) -> None:
        """Cleanup removes the pipeline run directory and closes file handles."""
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event())

        run_dir = tmp_path / "run_001"
        assert run_dir.is_dir()

        event_log.cleanup("run_001")

        assert not run_dir.exists()

    def test_read_nonexistent_run(self, tmp_path: Path) -> None:
        """Reading a nonexistent pipeline_run_id returns an empty list."""
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))

        result = event_log.read_events("nonexistent_run")

        assert result == []

    def test_corrupt_line_skipped(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Corrupt NDJSON lines are skipped with a warning."""
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(sequence=0))
        event_log.emit(make_trace_event(sequence=1))
        event_log.close()

        ndjson_file = tmp_path / "run_001" / "wf_wf_abc.ndjson"
        with open(ndjson_file, "a", encoding="utf-8") as fhandle:
            fhandle.write("not valid json\n")
            fhandle.write('{"event_kind": "pipe_start", "bad": true}\n')

        with caplog.at_level(logging.WARNING):
            result = event_log.read_events("run_001")

        assert len(result) == 2
        assert any("corrupt" in record.message.lower() or "skipping" in record.message.lower() for record in caplog.records)

    def test_multiprocess_concurrent_writes(self, tmp_path: Path) -> None:
        """Multiple processes writing to different workflow files produces no corruption."""
        traces_dir = str(tmp_path)
        pipeline_run_id = "run_001"
        events_per_worker = 10
        workflow_ids = ["wf_worker_0", "wf_worker_1", "wf_worker_2"]

        processes: list[multiprocessing.Process] = []
        for workflow_id in workflow_ids:
            proc = multiprocessing.Process(
                target=_worker_fn,
                args=(traces_dir, pipeline_run_id, workflow_id, events_per_worker),
            )
            processes.append(proc)

        for proc in processes:
            proc.start()
        for proc in processes:
            proc.join(timeout=30)

        for proc in processes:
            assert proc.exitcode == 0, f"Worker process exited with code {proc.exitcode}"

        reader = NdjsonEventLog(traces_dir=traces_dir)
        result = reader.read_events(pipeline_run_id)

        assert len(result) == len(workflow_ids) * events_per_worker

        ndjson_files = list((tmp_path / pipeline_run_id).glob("*.ndjson"))
        assert len(ndjson_files) == len(workflow_ids)

    def test_emit_after_cleanup_creates_fresh(self, tmp_path: Path) -> None:
        """Emitting after cleanup creates a fresh directory and file."""
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(sequence=0))
        event_log.cleanup("run_001")

        assert not (tmp_path / "run_001").exists()

        event_log.emit(make_trace_event(sequence=1))
        result = event_log.read_events("run_001")

        assert len(result) == 1
        assert result[0].sequence == 1
