"""DynamoDB-backed event log implementation.

Stores trace events in a DynamoDB table with the schema:
    PK: PIPELINE_RUN#{pipeline_run_id}
    SK: EVENT#{workflow_id}#{writer_id}#{sequence:010d}
    payload: dict (full event via model_dump)
    ttl: epoch seconds at which DynamoDB may delete the item, the write time plus the configured retention

Legacy emissions write writer_id="primary" so existing rows remain valid.

Compatible with the hosted trace-event DynamoDB adapter schema.
Requires: pip install "pipelex[dynamodb]"
"""

import threading
import time
from typing import Any

from pydantic import TypeAdapter, ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.system.exceptions import MissingDependencyError
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.exceptions import EventLogReadError, EventLogSchemaMismatchError, EventLogSetupError
from pipelex.tracing.trace_events import AnyTraceEvent, TraceEvent, json_invalid_message

try:
    import boto3
    from boto3.dynamodb.conditions import Key as DynamoKey
except ImportError:
    boto3 = None  # type: ignore[assignment]
    DynamoKey = None  # type: ignore[assignment, misc]

_any_trace_event_adapter: TypeAdapter[TraceEvent] = TypeAdapter(AnyTraceEvent)

_SECONDS_PER_DAY = 86_400


class DynamoDBEventLog(EventLogProtocol):
    """Event log backed by AWS DynamoDB.

    Write path: PutItem per event, synchronous. DynamoDB's PK+SK uniqueness
    provides natural deduplication for Temporal replay re-emissions.
    Read path: Query on PK, returns events sorted by SK which encodes
    (workflow_id, sequence) — matching the NDJSON ordering contract.
    Retention: every item carries a `ttl` in epoch seconds, `retention_days`
    past its write, which is the attribute the events table expires items on,
    so a run's events are deleted by DynamoDB instead of being kept forever.

    WARNING: Do not call emit() from inside a Temporal workflow body — the
    synchronous boto3 HTTP call will block the workflow thread and trigger
    the deadlock detector. Use BufferingEventLog + act_flush_trace_events instead.
    """

    def __init__(self, *, table_name: str, region: str, retention_days: int, writer_id: str = "primary") -> None:
        if boto3 is None:
            lib_name = "boto3"
            lib_extra_name = "dynamodb"
            msg = "boto3 is required for the DynamoDB event log backend."
            raise MissingDependencyError(lib_name, lib_extra_name, msg)
        # The config refuses a retention under one day too, but a direct construction bypasses it,
        # and such a retention would expire every event as it is written.
        if retention_days < 1:
            msg = f"The DynamoDB event log needs a retention of at least one day, got retention_days={retention_days}."
            raise EventLogSetupError(msg)

        self._table_name = table_name
        self._region = region
        self._writer_id = writer_id
        self._retention_seconds = retention_days * _SECONDS_PER_DAY
        self._sequence: int = 0
        self._sequence_lock = threading.Lock()
        # Translate construction-time botocore failures (e.g. a misconfigured region) into our
        # domain EventLogSetupError, mirroring the read_events boundary. Best-effort callers
        # (tracing assembly) catch the EventLogError base and degrade rather than aborting the run.
        from botocore.exceptions import (  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import
            BotoCoreError,
            ClientError,
        )

        try:
            dynamodb: Any = boto3.resource("dynamodb", region_name=self._region)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            self._table: Any = dynamodb.Table(self._table_name)  # pyright: ignore[reportUnknownMemberType]
        except (ClientError, BotoCoreError) as exc:
            msg = f"Failed to construct the DynamoDB event-log client for table={self._table_name} region={self._region}: {exc}"
            raise EventLogSetupError(msg) from exc

    @property
    @override
    def writer_id(self) -> str:
        return self._writer_id

    @override
    def next_sequence(self) -> int:
        """Return the next sequence number. Shared by all emitters.

        Guarded by a per-instance lock so concurrent activity threads
        sharing this backend cannot collide on the dedup key.
        """
        with self._sequence_lock:
            seq = self._sequence
            self._sequence += 1
            return seq

    @staticmethod
    def _make_pk(pipeline_run_id: str) -> str:
        return f"PIPELINE_RUN#{pipeline_run_id}"

    @staticmethod
    def _make_sk(workflow_id: str, *, writer_id: str, sequence: int) -> str:
        return f"EVENT#{workflow_id}#{writer_id}#{sequence:010d}"

    def _key_condition(self, pipeline_run_id: str) -> Any:
        """Build a KeyConditionExpression for querying by pipeline_run_id."""
        return DynamoKey("PK").eq(self._make_pk(pipeline_run_id))  # pyright: ignore[reportOptionalCall]

    @override
    def emit(self, event: TraceEvent) -> None:
        """Write a single event to DynamoDB. Synchronous and idempotent."""
        # The retention counts from the write rather than from the event's own timestamp, which is for display only.
        # A replay's re-emission overwrites the item under the same key and only pushes its expiry a little later.
        ttl = int(time.time()) + self._retention_seconds
        item: dict[str, Any] = {
            "PK": self._make_pk(event.pipeline_run_id),
            "SK": self._make_sk(event.workflow_id, writer_id=event.writer_id, sequence=event.sequence),
            "pipeline_run_id": event.pipeline_run_id,
            "workflow_id": event.workflow_id,
            "writer_id": event.writer_id,
            "sequence": event.sequence,
            "payload": event.model_dump_json(),
            "ttl": ttl,
        }
        self._table.put_item(Item=item)

    @override
    def read_events(self, pipeline_run_id: str) -> list[TraceEvent]:
        """Read all events for a pipeline run from DynamoDB.

        Store-level failures (throttling, auth, network) are translated into
        ``EventLogReadError`` so best-effort callers (graph assembly) can degrade
        gracefully without catching raw botocore exceptions. Individual
        unparseable items are skipped with a warning rather than failing the read.
        """
        from botocore.exceptions import (  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import
            BotoCoreError,
            ClientError,
        )

        items: list[dict[str, Any]] = []
        try:
            response = self._table.query(
                KeyConditionExpression=self._key_condition(pipeline_run_id),
                ScanIndexForward=True,
            )
            items.extend(response.get("Items", []))

            while "LastEvaluatedKey" in response:
                response = self._table.query(
                    KeyConditionExpression=self._key_condition(pipeline_run_id),
                    ScanIndexForward=True,
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                items.extend(response.get("Items", []))
        except (ClientError, BotoCoreError) as exc:
            msg = f"Failed to read trace events from DynamoDB for pipeline_run_id={pipeline_run_id}: {type(exc).__name__}"
            raise EventLogReadError(msg) from exc

        events: list[TraceEvent] = []
        refused_count = 0
        first_refusal: str | None = None
        for item in items:
            payload = item.get("payload")
            if payload is None:
                log.warning(
                    "A trace event item in DynamoDB has no payload, and was skipped",
                    fields={"pipeline_run_id": pipeline_run_id, "sort_key": item.get("SK")},
                )
                continue
            try:
                event = _any_trace_event_adapter.validate_json(payload)
            except ValidationError as exc:
                # `validate_json` reports unparseable input as a `json_invalid` entry rather than raising
                # `JSONDecodeError`, so the two cases are told apart by the error type. A payload the event
                # models refuse was stored whole, by a version whose event shape this one no longer accepts
                # — so it is counted and raised rather than skipped, which would have handed the caller a
                # silently truncated record of the run. This is the shape that persists across a rolling
                # deploy, where one image writes what another reads back.
                if (json_error := json_invalid_message(validation_error=exc)) is not None:
                    log.warning(
                        "A trace event item in DynamoDB is not valid JSON, and was skipped",
                        fields={"pipeline_run_id": pipeline_run_id, "sort_key": item.get("SK"), **error_fields(exc=exc, text=json_error)},
                    )
                    continue
                refused_count += 1
                if first_refusal is None:
                    first_refusal = f"PK={item.get('PK')} SK={item.get('SK')}: {format_pydantic_validation_error(exc)}"
                continue
            events.append(event)

        if refused_count:
            msg = (
                f"{refused_count} trace event(s) for pipeline_run_id={pipeline_run_id} are in a shape this version "
                f"does not accept, most likely written by an earlier one; run the pipeline again to get a log in the "
                f"current shape. First refusal: {first_refusal}"
            )
            raise EventLogSchemaMismatchError(msg)

        return events

    @override
    def close(self) -> None:
        """No-op: boto3 resources are reusable across calls."""

    @override
    def cleanup(self, pipeline_run_id: str) -> None:
        """Delete all events for a pipeline run, ahead of the expiry their `ttl` sets."""
        response = self._table.query(
            KeyConditionExpression=self._key_condition(pipeline_run_id),
            ProjectionExpression="PK, SK",
        )
        items: list[dict[str, Any]] = response.get("Items", [])
        while "LastEvaluatedKey" in response:
            response = self._table.query(
                KeyConditionExpression=self._key_condition(pipeline_run_id),
                ProjectionExpression="PK, SK",
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

        if not items:
            return

        with self._table.batch_writer() as writer:
            for item in items:
                writer.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
