"""Tests for NdjsonEventLog."""

import json
import logging
import multiprocessing
from pathlib import Path

import pytest

from pipelex.system.execution_chain import ExecutionAttempt, execution_chain_digest
from pipelex.tracing.exceptions import EventLogSchemaMismatchError
from pipelex.tracing.ndjson_event_log import NdjsonEventLog
from pipelex.tracing.trace_events import EdgeEvent, PipeStartEvent
from tests.unit.pipelex.tracing.conftest import make_edge_event, make_trace_event


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


def _only_run_file(run_dir: Path) -> Path:
    """The one file a run written by one attempt of one execution, through one writer, holds."""
    (ndjson_file,) = run_dir.glob("*.ndjson")
    return ndjson_file


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
        """Events of one chain, writer, kind and sequence are one event written twice, and are deduplicated."""
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(sequence=0))
        event_log.emit(make_trace_event(sequence=0))

        result = event_log.read_events("run_001")

        assert len(result) == 1

    def test_different_event_kinds_not_deduped(self, tmp_path: Path) -> None:
        """Events with same (workflow_id, sequence) but different event_kind are NOT deduped."""
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(workflow_id="wf_abc", sequence=0))
        event_log.emit(make_edge_event(workflow_id="wf_abc", sequence=0))

        result = event_log.read_events("run_001")

        assert len(result) == 2
        event_kinds = {type(evt) for evt in result}
        assert PipeStartEvent in event_kinds
        assert EdgeEvent in event_kinds

    def test_each_attempt_keeps_its_own_events(self, tmp_path: Path) -> None:
        """Attempts of one execution number their events from the same start, and every attempt's events are kept.

        They are read back attempt by attempt, an execution's earlier attempt first, and an execution dispatched under
        another attempt of its dispatcher is another chain.
        """
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(workflow_id="exec-item", sequence=0, attempt=2, lineage=[ExecutionAttempt(execution="exec-run", attempt=1)]))
        event_log.emit(make_trace_event(workflow_id="exec-item", sequence=0, attempt=1, lineage=[ExecutionAttempt(execution="exec-run", attempt=1)]))
        event_log.emit(make_trace_event(workflow_id="exec-item", sequence=0, attempt=1, lineage=[ExecutionAttempt(execution="exec-run", attempt=2)]))
        event_log.emit(make_trace_event(workflow_id="exec-item", sequence=0, attempt=2, lineage=[ExecutionAttempt(execution="exec-run", attempt=1)]))

        result = event_log.read_events("run_001")

        assert [event.chain_key for event in result] == ["exec-run@1/exec-item@1", "exec-run@1/exec-item@2", "exec-run@2/exec-item@1"]

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
        """Each workflow gets its own NDJSON file, named by the workflow and by its chain's digest."""
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(workflow_id="wf_alpha", sequence=0))
        event_log.emit(make_trace_event(workflow_id="wf_beta", sequence=0))

        run_dir = tmp_path / "run_001"
        ndjson_files = sorted(run_dir.glob("*.ndjson"))
        assert len(ndjson_files) == 2
        assert ndjson_files[0].name == f"wf_wf_alpha__c_{execution_chain_digest(chain_key='wf_alpha@1')}.ndjson"
        assert ndjson_files[1].name == f"wf_wf_beta__c_{execution_chain_digest(chain_key='wf_beta@1')}.ndjson"

    def test_each_attempt_of_each_execution_writes_its_own_file(self, tmp_path: Path) -> None:
        """Two attempts of one workflow, and one workflow two attempts of its dispatcher dispatched under one name, may
        write at once, each through a handle of its own: they never append to one file, where their partial lines could
        interleave and leave the whole run's log unreadable. The reader finds every file of the run.
        """
        run_1 = ExecutionAttempt(execution="exec-run", attempt=1)
        run_2 = ExecutionAttempt(execution="exec-run", attempt=2)
        chains: list[tuple[int, list[ExecutionAttempt]]] = [(1, [run_1]), (2, [run_1]), (1, [run_2])]
        writers = [NdjsonEventLog(traces_dir=str(tmp_path)) for _ in chains]
        for sequence in range(2):
            for writer, (attempt, lineage) in zip(writers, chains, strict=True):
                writer.emit(make_trace_event(workflow_id="exec-item", sequence=sequence, attempt=attempt, lineage=lineage))
        for writer in writers:
            writer.close()

        run_dir = tmp_path / "run_001"
        ndjson_files = sorted(run_dir.glob("*.ndjson"))
        assert len(ndjson_files) == len(chains)
        for ndjson_file in ndjson_files:
            assert ndjson_file.name.startswith("wf_exec-item__c_")
            assert len(ndjson_file.read_text(encoding="utf-8").splitlines()) == 2

        result = NdjsonEventLog(traces_dir=str(tmp_path)).read_events("run_001")
        assert [(event.chain_key, event.sequence) for event in result] == [
            ("exec-run@1/exec-item@1", 0),
            ("exec-run@1/exec-item@1", 1),
            ("exec-run@1/exec-item@2", 0),
            ("exec-run@1/exec-item@2", 1),
            ("exec-run@2/exec-item@1", 0),
            ("exec-run@2/exec-item@1", 1),
        ]

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
        """A line that is not JSON at all is a half-written record from a crash mid-write, so it is skipped
        with a warning and the rest of the log — which is still the run's own record — is returned.
        """
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(sequence=0))
        event_log.emit(make_trace_event(sequence=1))
        event_log.close()

        ndjson_file = _only_run_file(tmp_path / "run_001")
        with open(ndjson_file, "a", encoding="utf-8") as fhandle:
            fhandle.write("not valid json\n")

        with caplog.at_level(logging.WARNING):
            result = event_log.read_events("run_001")

        assert len(result) == 2
        assert any("corrupt" in record.message.lower() or "skipping" in record.message.lower() for record in caplog.records)

    def test_a_skipped_line_is_named_by_its_place_and_never_quoted(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """The warning says where the line is and where its parse stopped, and carries none of the line itself.

        A half-written line is a traced event cut short, so it holds the run's values; pydantic's own text
        for the failure quotes it whole. The warning takes the parse error's message instead, which only
        says where the parse stopped.
        """
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(sequence=0))
        event_log.close()
        ndjson_file = _only_run_file(tmp_path / "run_001")
        with open(ndjson_file, "a", encoding="utf-8") as fhandle:
            fhandle.write('{"event_kind": "pipe_start", "traced_value": "a_value_from_the_run\n')

        with caplog.at_level(logging.WARNING):
            event_log.read_events("run_001")

        (record,) = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert record.getMessage() == "A corrupt line of a trace event log, not valid JSON, was skipped"
        attributes = vars(record)
        assert attributes["file.path"] == str(ndjson_file)
        assert attributes["line_number"] == 2
        assert attributes["error.type"] == "ValidationError"
        assert attributes["error.message"].startswith("Invalid JSON")
        assert "a_value_from_the_run" not in repr(attributes)

    def test_a_line_the_event_models_refuse_raises_instead_of_vanishing(self, tmp_path: Path) -> None:
        """A line that parses as JSON and is then refused was written whole, by a version whose event shape
        this one no longer accepts. Skipping those returned an old run's log as an empty list, which every
        caller read as a run that recorded nothing — so the read refuses instead, and says how many and why.
        """
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(sequence=0))
        event_log.close()

        ndjson_file = _only_run_file(tmp_path / "run_001")
        with open(ndjson_file, "a", encoding="utf-8") as fhandle:
            fhandle.write('{"event_kind": "pipe_start", "bad": "traced-value"}\n')

        with pytest.raises(EventLogSchemaMismatchError) as refusal:
            event_log.read_events("run_001")

        assert "1 trace event(s)" in str(refusal.value)
        assert "run the pipeline again" in str(refusal.value)

    def test_a_refusal_does_not_quote_the_refused_event(self, tmp_path: Path) -> None:
        """The refusal travels into the run's assembly errors, and from there into API responses and the
        persisted usage file, so it names the fields it refused without quoting the traced values they held.
        """
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(sequence=0))
        event_log.close()

        ndjson_file = _only_run_file(tmp_path / "run_001")
        with open(ndjson_file, "a", encoding="utf-8") as fhandle:
            fhandle.write('{"event_kind": "pipe_start", "bad": "traced-value"}\n')

        with pytest.raises(EventLogSchemaMismatchError) as refusal:
            event_log.read_events("run_001")

        assert "traced-value" not in str(refusal.value)

    def test_a_refusal_locates_the_field_and_never_quotes_the_value_it_held(self, tmp_path: Path) -> None:
        """A refused field holding a traced value: the refusal names the field by the event models' schema, never the value."""
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(sequence=0))
        event_log.close()

        ndjson_file = _only_run_file(tmp_path / "run_001")
        refused_line = json.loads(make_trace_event(sequence=1).model_dump_json())
        refused_line["sequence"] = "traced-value-from-the-run"
        with open(ndjson_file, "a", encoding="utf-8") as fhandle:
            fhandle.write(json.dumps(refused_line) + "\n")

        with pytest.raises(EventLogSchemaMismatchError) as refusal:
            event_log.read_events("run_001")

        assert f"{refused_line['event_kind']}.sequence: Input should be a valid integer" in str(refusal.value)
        assert "traced-value-from-the-run" not in str(refusal.value)

    def test_a_line_naming_no_execution_is_refused_with_the_others(self, tmp_path: Path) -> None:
        """A line whose `workflow_id` is empty names no execution: it is counted with the lines the models refuse,
        rather than read and then failing whoever first asks for its chain.
        """
        event_log = NdjsonEventLog(traces_dir=str(tmp_path))
        event_log.emit(make_trace_event(sequence=0))
        event_log.close()

        ndjson_file = _only_run_file(tmp_path / "run_001")
        nameless_line = make_trace_event(sequence=1).model_dump_json().replace('"workflow_id":"wf_abc"', '"workflow_id":""')
        assert '"workflow_id":""' in nameless_line
        with open(ndjson_file, "a", encoding="utf-8") as fhandle:
            fhandle.write(nameless_line + "\n")

        with pytest.raises(EventLogSchemaMismatchError, match="1 trace event"):
            event_log.read_events("run_001")

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
