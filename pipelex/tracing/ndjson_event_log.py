"""NDJSON file-based event log implementation.

One JSON event per line, one file per workflow, organized by pipeline run:
    {traces_dir}/{pipeline_run_id}/wf_{workflow_id}.ndjson
"""

import json
import os
import shutil
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
    deduplicates by (workflow_id, sequence), and sorts deterministically.
    """

    def __init__(self, traces_dir: str) -> None:
        self._traces_dir = traces_dir
        self._file_handles: dict[tuple[str, str], IO[str]] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @override
    def emit(self, event: TraceEvent) -> None:
        """Append event as a JSON line, flush immediately.

        Creates the run directory on first write. Caches file handles
        to avoid repeated open() calls for high-frequency events.
        """
        cache_key = (event.pipeline_run_id, event.workflow_id)
        handle = self._file_handles.get(cache_key)

        if handle is None:
            run_dir = os.path.join(self._traces_dir, event.pipeline_run_id)
            os.makedirs(run_dir, exist_ok=True)
            file_path = os.path.join(run_dir, f"wf_{event.workflow_id}.ndjson")
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

        seen: set[tuple[str, int]] = set()
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

                    dedup_key = (event.workflow_id, event.sequence)
                    if dedup_key not in seen:
                        seen.add(dedup_key)
                        events.append(event)

        events.sort(key=lambda evt: (evt.workflow_id, evt.sequence))
        return events

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    @override
    def cleanup(self, pipeline_run_id: str) -> None:
        """Close cached file handles and remove the run directory."""
        keys_to_remove = [key for key in self._file_handles if key[0] == pipeline_run_id]
        for key in keys_to_remove:
            self._file_handles[key].close()
            del self._file_handles[key]

        run_dir = os.path.join(self._traces_dir, pipeline_run_id)
        if os.path.isdir(run_dir):
            shutil.rmtree(run_dir)

    def close(self) -> None:
        """Close all cached file handles."""
        for handle in self._file_handles.values():
            handle.close()
        self._file_handles.clear()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # noqa: S110
            # Safety net during interpreter shutdown — logging may not be available
            pass
