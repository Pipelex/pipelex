"""NDJSON file-based event log implementation.

One JSON event per line, one file per workflow, organized by pipeline run:
    {traces_dir}/{pipeline_run_id}/wf_{workflow_id}.ndjson
"""

import json
import os
import shutil
import threading
from pathlib import Path
from typing import IO

from pydantic import TypeAdapter, ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.trace_events import AnyTraceEvent, TraceEvent

_any_trace_event_adapter: TypeAdapter[TraceEvent] = TypeAdapter(AnyTraceEvent)


class NdjsonEventLog(EventLogProtocol):
    """Event log backed by NDJSON files on the local filesystem.

    Write path: appends one JSON line per event, flushed immediately.
    Read path: globs all .ndjson files in the run directory, parses,
    deduplicates by (workflow_id, writer_id, type, sequence), and sorts
    by (workflow_id, sequence, writer_id) — sequence primary so a
    runner-side writer's events do not sort before earlier router events.

    Multi-writer file naming: events from writer_id="primary" land in the
    legacy file `wf_{workflow_id}.ndjson`; events from any other writer
    land in `wf_{workflow_id}__w_{writer_id}.ndjson`. The file-handle cache
    key is `(pipeline_run_id, workflow_id, writer_id)` so two writers
    emitting concurrently never share a stale handle.

    For multi-process / multi-host deployments, traces_dir must be a
    filesystem visible to all writer processes (NFS/EFS); use the
    DynamoDB backend for fully separated hosts.
    """

    def __init__(self, traces_dir: str, writer_id: str = "primary") -> None:
        self._traces_dir = traces_dir
        self._file_handles: dict[tuple[str, str, str], IO[str]] = {}
        self._sequence: int = 0
        self._sequence_lock = threading.Lock()
        self._handles_lock = threading.Lock()
        self._writer_id = writer_id

    @property
    @override
    def writer_id(self) -> str:
        return self._writer_id

    @override
    def next_sequence(self) -> int:
        """Return the next sequence number. Shared by all emitters.

        The increment is guarded by a per-instance lock so concurrent activity
        threads sharing this backend (via ``get_or_create_activity_event_log``)
        cannot read the same value before either increments — duplicate
        sequence numbers would collide on the
        ``(workflow_id, writer_id, type, sequence)`` dedup key and silently
        drop one event.
        """
        with self._sequence_lock:
            seq = self._sequence
            self._sequence += 1
            return seq

    @staticmethod
    def _file_name_for(workflow_id: str, writer_id: str) -> str:
        """File name for a (workflow_id, writer_id) pair.

        Child workflow IDs now use ``/`` as a path separator (e.g.
        ``ut-{uuid}/step_two-9a262f1f``); replace it with ``__`` so the
        derived file name stays flat inside the run directory.

        The legacy single-writer name is preserved when writer_id="primary"
        so existing files continue to be written and read correctly.
        """
        safe_id = workflow_id.replace("/", "__")
        if writer_id == "primary":
            return f"wf_{safe_id}.ndjson"
        return f"wf_{safe_id}__w_{writer_id}.ndjson"

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @override
    def emit(self, event: TraceEvent) -> None:
        """Append event as a JSON line, flush immediately.

        Creates the run directory on first write. Caches file handles
        keyed by (pipeline_run_id, workflow_id, writer_id) to avoid
        repeated open() calls for high-frequency events.
        """
        cache_key = (event.pipeline_run_id, event.workflow_id, event.writer_id)
        handle = self._file_handles.get(cache_key)

        if handle is None:
            with self._handles_lock:
                handle = self._file_handles.get(cache_key)
                if handle is None:
                    run_dir = os.path.join(self._traces_dir, event.pipeline_run_id)
                    os.makedirs(run_dir, exist_ok=True)
                    file_path = os.path.join(run_dir, self._file_name_for(event.workflow_id, event.writer_id))
                    handle = open(file_path, "a", encoding="utf-8")  # noqa: SIM115
                    self._file_handles[cache_key] = handle

        handle.write(event.model_dump_json() + "\n")
        handle.flush()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @override
    def read_events(self, pipeline_run_id: str) -> list[TraceEvent]:
        """Read all events for a pipeline run from NDJSON files.

        Deduplicates by (workflow_id, sequence) to handle Temporal replay
        re-emission. Sorts by (workflow_id, sequence) for deterministic ordering.
        Corrupt lines (truncated JSON from crash-mid-write) are skipped with
        a warning log.
        """
        run_dir = os.path.join(self._traces_dir, pipeline_run_id)
        if not os.path.isdir(run_dir):
            return []

        ndjson_files = sorted(Path(run_dir).glob("*.ndjson"))

        seen: set[tuple[str, str, str, int]] = set()
        events: list[TraceEvent] = []

        for ndjson_path in ndjson_files:
            file_path = str(ndjson_path)
            with open(file_path, encoding="utf-8") as fhandle:
                for line_number, raw_line in enumerate(fhandle, start=1):
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    try:
                        event = _any_trace_event_adapter.validate_json(stripped)
                    except (ValidationError, json.JSONDecodeError) as exc:
                        log.warning(f"Skipping corrupt line in {file_path}:{line_number} — {exc}")
                        continue

                    dedup_key = (event.workflow_id, event.writer_id, type(event).__name__, event.sequence)
                    if dedup_key not in seen:
                        seen.add(dedup_key)
                        events.append(event)

        # TODO: causal ordering — sorting by (workflow_id, sequence) groups by lexicographic
        # workflow ID, not execution order. In parent/child workflow topologies this can cause
        # incorrect producer map overwrites in GraphSpecAssembler. Consider timestamp-based
        # or topology-aware ordering.
        events.sort(key=lambda evt: (evt.workflow_id, evt.sequence, evt.writer_id))
        return events

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    @override
    def cleanup(self, pipeline_run_id: str) -> None:
        """Close cached file handles and remove the run directory."""
        keys_to_remove = [key for key in self._file_handles if key[0] == pipeline_run_id]
        for cache_key in keys_to_remove:
            self._file_handles[cache_key].close()
            del self._file_handles[cache_key]

        run_dir = os.path.join(self._traces_dir, pipeline_run_id)
        if os.path.isdir(run_dir):
            shutil.rmtree(run_dir)

    @override
    def close(self) -> None:
        """Close all cached file handles."""
        for handle in self._file_handles.values():
            handle.close()
        self._file_handles.clear()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # noqa: BLE001, S110
            # Safety net during interpreter shutdown — logging may not be available
            pass
