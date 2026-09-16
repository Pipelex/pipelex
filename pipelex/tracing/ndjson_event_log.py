"""NDJSON file-based event log implementation.

One JSON event per line, one file per workflow, organized by pipeline run:
    {traces_dir}/{pipeline_run_id}/wf_{workflow_id}.ndjson
"""

import shutil
import threading
from pathlib import Path
from typing import IO

from pydantic import TypeAdapter, ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.exceptions import EventLogSchemaMismatchError
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

    def __init__(self, traces_dir: str | Path, writer_id: str = "primary") -> None:
        self._traces_dir = Path(traces_dir)
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
    def _file_name_for(workflow_id: str, *, writer_id: str) -> str:
        """File name for a (workflow_id, writer_id) pair.

        Workflow ids use ``_`` as their separator and so should not contain
        ``/`` (e.g. ``ut-{uuid}_step_two-9a262f1f``). The ``replace`` below is a
        defensive guard that keeps the derived file name flat inside the run
        directory even if a ``/`` ever slips into an id.

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
                    run_dir = self._traces_dir / event.pipeline_run_id
                    run_dir.mkdir(parents=True, exist_ok=True)
                    file_path = run_dir / self._file_name_for(event.workflow_id, writer_id=event.writer_id)
                    handle = open(file_path, "a", encoding="utf-8")  # ruff: ignore[open-file-with-context-handler]
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

        A line that parses as JSON but is refused by the event models is not corrupt — it was written
        whole, by a version whose event shape this one no longer accepts — so it raises
        :class:`EventLogSchemaMismatchError` rather than being skipped. Skipping those returned an old
        run's log as an empty list, which every caller read as a run that simply recorded nothing.
        """
        run_dir = self._traces_dir / pipeline_run_id
        if not run_dir.is_dir():
            return []

        ndjson_files = sorted(run_dir.glob("*.ndjson"))

        seen: set[tuple[str, str, str, int]] = set()
        events: list[TraceEvent] = []
        refused_count = 0
        first_refusal: str | None = None

        for ndjson_path in ndjson_files:
            with open(ndjson_path, encoding="utf-8") as fhandle:
                for line_number, raw_line in enumerate(fhandle, start=1):
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    try:
                        event = _any_trace_event_adapter.validate_json(stripped)
                    except ValidationError as validation_error:
                        # `validate_json` reports unparseable input as a `json_invalid` entry rather than
                        # raising `JSONDecodeError`, so the two cases are told apart by the error type and
                        # not by the exception class: a line that is not JSON is the half-written record of
                        # a crash mid-write and is skipped, while one that parses and is then refused was
                        # written whole by a version whose event shape this one no longer accepts. The refusal
                        # names fields rather than quoting them: it travels into the run's assembly errors, and
                        # the pydantic error's own text quotes the traced values it refused.
                        if any(error["type"] == "json_invalid" for error in validation_error.errors()):
                            log.warning(f"Skipping corrupt line in {ndjson_path}:{line_number} — {validation_error}")
                            continue
                        refused_count += 1
                        if first_refusal is None:
                            first_refusal = f"{ndjson_path}:{line_number} — {format_pydantic_validation_error(validation_error)}"
                        continue

                    dedup_key = (event.workflow_id, event.writer_id, type(event).__name__, event.sequence)
                    if dedup_key not in seen:
                        seen.add(dedup_key)
                        events.append(event)

        if refused_count:
            msg = (
                f"{refused_count} trace event(s) for pipeline_run_id={pipeline_run_id} are in a shape this version "
                f"does not accept, most likely written by an earlier one; run the pipeline again to get a log in the "
                f"current shape. First refusal: {first_refusal}"
            )
            raise EventLogSchemaMismatchError(msg)

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

        run_dir = self._traces_dir / pipeline_run_id
        if run_dir.is_dir():
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
        except Exception:  # ruff: ignore[blind-except, try-except-pass]
            # Safety net during interpreter shutdown — logging may not be available
            pass
